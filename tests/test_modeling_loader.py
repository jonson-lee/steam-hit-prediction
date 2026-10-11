"""Consumer boundaries tested with temporary synthetic CSVs and real decoding.

Only the formal verifier is mocked in semantic tests: a synthetic package must
never become a formal accepted package. An unmocked test checks that refusal.
"""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import pandas as pd

import config
from scripts import load_modeling_data as loader
from src import steam_handoff as handoff


def source_row(key, year, **changes):
    row = dict(appid=key, name="Synthetic game", release_date=f"{year}-01-01",
               english="1", required_age="0", developer="A", publisher="P",
               platforms="windows", categories="Action", genres="Indie",
               positive_ratings="10", negative_ratings="0")
    row.update(changes)
    return row


class ModelingLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix="steam-modeling-fixture-")
        rows = [source_row("001", 2015, developer="unknown", english="", required_age="nan"),
                source_row("12", 2016, developer=";;", platforms=";;",
                           required_age="9223372036854775807"),
                source_row("13", 2017, positive_ratings="20"),
                source_row("14", 2018, positive_ratings="30"),
                source_row("15", 2019)]
        data = handoff.build_dataset(rows)
        receipt = handoff.write_package(data, cls.fixture_temp.name, scope="synthetic")
        if receipt["report"]["overall"] != "pass":
            raise AssertionError(receipt["report"])
        cls.fixture = receipt["directory"]
        cls.schema, cls.definitions = handoff._load_spec()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="steam-modeling-test-")
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / "package"
        shutil.copytree(self.fixture, self.package)

    def accepted_verifier(self):
        return mock.patch.object(loader.handoff, "verify_package", return_value={
            "overall": "pass", "accepted_for_formal_handoff": True,
            "checks": {"stable_hashes": True},
        })

    def table(self, name):
        logical = f"handoff/{name}.csv"
        return handoff.read_table(self.package / logical, self.schema["files"][logical]["columns"],
                                  self.definitions, logical)

    def rewrite(self, name, rows):
        logical = f"handoff/{name}.csv"
        path = self.package / logical
        path.unlink()
        handoff.write_table(path, rows, self.schema["files"][logical]["columns"],
                            self.definitions, logical)

    def test_requires_formal_physical_ready(self):
        with self.assertRaisesRegex(ValueError, "Formal handoff verification failed"):
            loader.load_modeling_data(self.package)

    def test_consumer_failure_stops_before_reading_tables(self):
        with mock.patch.object(loader.handoff, "verify_package", return_value={
                "overall": "fail", "accepted_for_formal_handoff": False,
                "checks": {"stable_hashes": False}}), mock.patch.object(loader.handoff, "read_table") as reader:
            with self.assertRaisesRegex(ValueError, "stable_hashes"):
                loader.load_modeling_data(self.package)
            reader.assert_not_called()

    def test_aligned_whitelist_and_exact_wire_types(self):
        with self.accepted_verifier() as verifier:
            data = loader.load_modeling_data(self.package)
        verifier.assert_called_once_with(self.package.resolve(), require_real=True)
        self.assertEqual(tuple(data), ("train", "validation", "test"))
        for split, expected_rows in (("train", 2), ("validation", 1), ("test", 1)):
            part = data[split]
            self.assertEqual(len(part["X"]), expected_rows)
            self.assertEqual(list(part["X"].columns), list(config.PRIMARY_FEATURE_COLUMNS))
            self.assertEqual(list(part["y"].columns), ["hit_reviews"])
            for frame in part.values():
                self.assertTrue(frame.index.equals(part["X"].index))
                self.assertTrue(all(isinstance(key, str) for key in frame.index))
            self.assertFalse(set(part["X"].columns) &
                             (set(config.FORBIDDEN_PREDICTOR_COLUMNS) | set(config.METADATA_COLUMNS)))
        train = data["train"]
        self.assertEqual(train["X"].index.tolist(), ["001", "12"])
        self.assertIsNone(train["X"].loc["001", "developer"])
        self.assertEqual(train["X"].loc["12", "developer"], [])
        self.assertEqual(train["states"].loc["001", "developer"], "S_MISSING")
        self.assertEqual(train["states"].loc["12", "developer"], "S_EMPTY_LIST")
        self.assertEqual(train["X"].loc["001", "platforms"], ["windows"])
        self.assertTrue(bool(train["X"].loc["001", "has_windows"]))
        self.assertFalse(bool(train["X"].loc["12", "has_windows"]))
        self.assertTrue(pd.isna(train["X"].loc["001", "english"]))
        self.assertEqual(str(train["X"].english.dtype), "Int8")
        self.assertEqual(int(train["X"].loc["12", "required_age"]), 9223372036854775807)
        self.assertEqual(str(train["X"].required_age.dtype), "Int64")
        self.assertEqual(train["X"].loc["12", "dev_prior_count"], self.table("x_primary")[1]["dev_prior_count"])

    def test_reorders_each_table_by_appid_without_misalignment(self):
        with self.accepted_verifier():
            expected = loader.load_modeling_data(self.package)
        for name in ("x_primary", "y_label", "keys_meta", "x_entity_states"):
            self.rewrite(name, list(reversed(self.table(name))))
        with self.accepted_verifier():
            actual = loader.load_modeling_data(self.package)
        for split in expected:
            for name in expected[split]:
                pd.testing.assert_frame_equal(actual[split][name], expected[split][name])

    def test_duplicate_or_missing_key_is_rejected_in_every_join_table(self):
        for name in ("x_primary", "y_label", "x_entity_states"):
            original = self.table(name)
            for mutation in ("duplicate", "mismatch"):
                with self.subTest(table=name, mutation=mutation):
                    rows = deepcopy(original)
                    rows[1]["appid"] = rows[0]["appid"] if mutation == "duplicate" else "999"
                    self.rewrite(name, rows)
                    with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "Duplicate appid|key domains differ"):
                        loader.load_modeling_data(self.package)
                    self.rewrite(name, original)

    def test_metadata_duplicate_key_is_rejected(self):
        rows = self.table("keys_meta")
        rows[1]["appid"] = rows[0]["appid"]
        self.rewrite("keys_meta", rows)
        with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "Duplicate appid in metadata"):
            loader.load_modeling_data(self.package)

    def test_target_audit_fields_cannot_enter_feature_schema(self):
        path = self.package / "manifest/handoff_schema.json"
        schema = json.loads(path.read_text())
        schema["files"]["handoff/x_primary.csv"]["columns"].append("total_ratings")
        path.write_text(json.dumps(schema), encoding="utf-8")
        with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "24-column whitelist"):
            loader.load_modeling_data(self.package)

    def test_config_snapshot_mismatch_is_rejected(self):
        path = self.package / "manifest/design_contract_snapshot.json"
        snapshot = json.loads(path.read_text())
        snapshot["config_sha256"] = "0" * 64
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "configuration snapshot"):
            loader.load_modeling_data(self.package)

    def test_split_year_mismatch_is_rejected(self):
        rows = self.table("keys_meta")
        rows[2]["release_year"] = config.TEST_YEAR
        self.rewrite("keys_meta", rows)
        with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "release-year split"):
            loader.load_modeling_data(self.package)

    def test_invalid_binary_label_is_rejected(self):
        rows = self.table("y_label")
        rows[0]["hit_reviews"] = 2
        self.rewrite("y_label", rows)
        with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "nonmissing binary"):
            loader.load_modeling_data(self.package)

    def test_sequence_null_and_empty_state_mismatch_is_rejected(self):
        rows = self.table("x_entity_states")
        rows[0]["developer"] = "S_EMPTY_LIST"
        self.rewrite("x_entity_states", rows)
        with self.accepted_verifier(), self.assertRaisesRegex(ValueError, "Sequence state"):
            loader.load_modeling_data(self.package)


if __name__ == "__main__":
    unittest.main()
