"""B04-T02 runner for the ten statically accepted stage-0 boundary cases.

Frozen baseline referenced by this file (declared by GPT for STEAM-B04/B04-T02/R0;
this runner compares against them and never re-derives or re-declares them):

    Git HEAD                                  e8c1a8a085539a70ccaa935c520b2c0ff79724b1
    H04 schema                                stage0_precheck.h04_r4
    baseline_schema                           stage0_precheck.h04_gpt_r3
    scripts/stage0_precheck.py                17791770d9d3f0f4fb0a6fe3774e7a5816b88f8b4d86f28b5e2bf81f465a9dd6
    tests/fixtures/stage0_boundary_cases.json 18d36645b87837f2614c6809dbf30b380ea6b686a944d19f572d7ffc9dfb5968
    config.py                                 63991ed1e5033d0f5e885f4747c6b95339e0fbeb4f53cefb878ab11571eeb91e

Case -> test method map (the only coverage claimed by this module):

    C-01  test_c01_audit_appid_empty_and_whitespace_counts
    C-02  test_c02_audit_appid_whitespace_duplicate_bases
    C-03  test_c03_audit_appid_strip_duplicate_blocker
    C-04  test_c04_audit_numeric_overflow_is_not_finite
    C-05  test_c05_audit_entity_field_inline_missing (2 columns x 2 values = 4 calls)
    C-06  test_c06_audit_entity_field_empty_token_and_dedup (2 columns x 2 values = 4 calls)
    C-07  test_c07_main_flow_date_window_utc_nat_and_2018_isolation
    C-08  test_c08_main_flow_read_failure_paths (C-08a missing column, C-08b encoding)
    C-09  test_c09_restricted_read_usecols_and_read_parameters
    C-10  test_c10_clean_baseline_pending_items_not_a_blocker

Scope discipline: read-only with respect to the project. Every synthetic CSV lives in a
TemporaryDirectory, the candidate is only ever handed those paths, and each run compares the
directory listing plus the input byte hashes before and after the call. The file never reads the
two synthetic sentinel columns of C-09, never imports or instantiates a model, never installs
anything, and never skips: a baseline mismatch fails the whole module.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np  # noqa: F401  (required by the candidate; presence is asserted below)
import pandas as pd

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = PROJECT_ROOT / "scripts" / "stage0_precheck.py"
CONFIG_PATH = PROJECT_ROOT / "config.py"
SPEC_PATH = PROJECT_ROOT / "tests" / "fixtures" / "stage0_boundary_cases.json"

# Referenced bound hashes. Compared, never treated as computed evidence.
BOUND_SHA256 = {
    "scripts/stage0_precheck.py":
        "17791770d9d3f0f4fb0a6fe3774e7a5816b88f8b4d86f28b5e2bf81f465a9dd6",
    "config.py":
        "63991ed1e5033d0f5e885f4747c6b95339e0fbeb4f53cefb878ab11571eeb91e",
    "tests/fixtures/stage0_boundary_cases.json":
        "18d36645b87837f2614c6809dbf30b380ea6b686a944d19f572d7ffc9dfb5968",
}

REQUIRED_COLUMNS = (
    "appid", "release_date", "english", "developer", "publisher",
    "platforms", "required_age", "categories", "genres",
)

# The 13 planned stages, written out by hand from the frozen spec so that the
# coverage partition is never computed from the code under test.
PLANNED_STAGES = (
    "input_exists", "config", "environment", "header", "read", "header_names",
    "appid", "dates", "scope", "english", "required_age", "entities",
    "multivalue",
)

# Stages that cannot have run on either read-failure path of C-08.
POST_READ_STAGES = ("dates", "scope", "english", "required_age", "entities",
                    "multivalue")

CANDIDATE = None
CONFIG = None
SPEC = None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot(directory):
    """Listing plus content hashes of every file under directory."""
    entries = {}
    for path in sorted(Path(directory).rglob("*")):
        if path.is_file():
            entries[str(path.relative_to(directory))] = [
                path.stat().st_size, _sha256(path)]
    return entries


def _case(case_id):
    for case in SPEC["cases"]:
        if case["id"] == case_id:
            return case
    raise AssertionError("case id absent from the bound spec: " + case_id)


def _baseline_rows():
    frame_spec = SPEC["valid_baseline_frame"]
    columns = list(frame_spec["columns"])
    if columns != list(REQUIRED_COLUMNS):
        raise AssertionError(
            "bound baseline columns are not the 9 required columns: "
            + repr(columns))
    return [dict(row) for row in frame_spec["rows"]]


def _write_csv(directory, name, columns, rows):
    path = Path(directory) / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns),
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})
    return path


def _run_cli(csv_path, encoding=None):
    """Real subprocess run: the process exit code is the evidence, not main()."""
    argv = [sys.executable, "-B", str(CANDIDATE_PATH),
            "--input-main", str(csv_path), "--tree", "rf"]
    if encoding is not None:
        argv += ["--encoding", encoding]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(argv, cwd=str(PROJECT_ROOT), capture_output=True,
                          text=True, check=False, env=environment)


def _reject_json_constant(token):
    raise AssertionError(
        "stdout JSON contains a non-finite constant: " + str(token))


def _parse_stdout(stdout):
    """Parse the whole stdout as exactly one JSON object; no line/brace slicing."""
    try:
        value = json.loads(stdout, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "stdout is not exactly one JSON document: " + repr(exc)) from exc
    if not isinstance(value, dict):
        raise AssertionError(
            "stdout JSON is not an object: " + type(value).__name__)
    return value


def _stages(records):
    return {record["stage"] for record in records}


def setUpModule():
    """Fail closed before any candidate code is imported or executed."""
    global CANDIDATE, CONFIG, SPEC

    problems = []
    for relative, expected in sorted(BOUND_SHA256.items()):
        path = PROJECT_ROOT / relative
        if not path.is_file():
            problems.append("missing bound artefact: " + relative)
            continue
        actual = _sha256(path)
        if actual != expected:
            problems.append("hash mismatch for " + relative
                            + ": expected " + expected + ", actual " + actual)
    if problems:
        raise AssertionError(
            "Frozen baseline drift; refusing to run any case and refusing to "
            "swap baselines:\n  " + "\n  ".join(problems))

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    CONFIG = importlib.import_module("config")
    if Path(CONFIG.__file__).resolve() != CONFIG_PATH:
        raise AssertionError("config resolved to "
                            + str(Path(CONFIG.__file__).resolve())
                            + " instead of " + str(CONFIG_PATH))

    # Equivalent to "from scripts import stage0_precheck", deferred so that the
    # hash gate above always runs before the candidate module is imported.
    CANDIDATE = importlib.import_module("scripts.stage0_precheck")
    if Path(CANDIDATE.__file__).resolve() != CANDIDATE_PATH:
        raise AssertionError("candidate resolved to "
                            + str(Path(CANDIDATE.__file__).resolve())
                            + " instead of " + str(CANDIDATE_PATH))


class Stage0PrecheckBoundaryCaseTests(unittest.TestCase):
    maxDiff = None

    # ------------------------------------------------------------------
    # baseline gate
    # ------------------------------------------------------------------
    def test_00_baseline_hashes_and_module_paths(self):
        self.assertEqual(len(PLANNED_STAGES), 13)
        for relative, expected in sorted(BOUND_SHA256.items()):
            with self.subTest(bound=relative):
                self.assertEqual(_sha256(PROJECT_ROOT / relative), expected,
                                 "bound baseline artefact changed: " + relative)
        self.assertEqual(Path(CONFIG.__file__).resolve(), CONFIG_PATH)
        self.assertEqual(Path(CANDIDATE.__file__).resolve(), CANDIDATE_PATH)
        # Static contract binding: the 13 planned stages are exactly the spec's.
        self.assertEqual(tuple(stage for stage, _ in CANDIDATE.CHECK_STAGES),
                         PLANNED_STAGES)
        for stage, description in CANDIDATE.CHECK_STAGES:
            with self.subTest(stage=stage):
                self.assertIsInstance(description, str)
                self.assertNotEqual(description, "")
        # numpy/pandas are hard requirements here: a missing dependency must be
        # an explicit failure, never a skip.
        self.assertIsNotNone(np)
        self.assertIsNotNone(pd)

    # ------------------------------------------------------------------
    # component cases C-01 .. C-06
    # ------------------------------------------------------------------
    def _component_frame(self, column, value):
        """Minimal frame: the audited column only, no underscore padding."""
        frame = pd.DataFrame({column: [value]})
        mask = pd.Series([True], index=frame.index)
        return frame, mask

    def test_c01_audit_appid_empty_and_whitespace_counts(self):
        frame = pd.DataFrame({"appid": ["", "   ", "10"]})
        report, blockers = CANDIDATE.audit_appid(frame)
        self.assertIsInstance(report, dict)
        self.assertIsInstance(blockers, dict)
        self.assertEqual(report["rows_total"], 3)
        self.assertEqual(report["empty_cell"], 1)
        self.assertEqual(report["whitespace_only_cell"], 1)
        # The two classes are mutually exclusive: 1 empty + 1 whitespace-only.
        self.assertEqual(
            report["empty_cell"] + report["whitespace_only_cell"], 2)
        for key in ("empty_cell", "whitespace_only_cell",
                    "duplicate_raw_value_rows", "duplicate_after_strip_rows"):
            with self.subTest(count=key):
                self.assertIsInstance(report[key], int)
                self.assertGreaterEqual(report[key], 0)
        self.assertEqual(report["duplicate_raw_value_rows"], 0)
        self.assertEqual(report["duplicate_after_strip_rows"], 0)
        # Missingness blocks; duplicates must not be reported.
        self.assertEqual(set(blockers), {"APPID_MISSING"})

    def test_c02_audit_appid_whitespace_duplicate_bases(self):
        frame = pd.DataFrame({"appid": [" ", " "]})
        report, blockers = CANDIDATE.audit_appid(frame)
        self.assertEqual(report["rows_total"], 2)
        self.assertEqual(report["duplicate_raw_value_rows"], 2)
        self.assertEqual(report["duplicate_after_strip_rows"], 0)
        for key in ("duplicate_raw_value_rows", "duplicate_after_strip_rows"):
            with self.subTest(count=key):
                self.assertIsInstance(report[key], int)
                self.assertGreaterEqual(report[key], 0)
        # duplicated(keep=False) basis: every participating row is counted, so
        # two identical rows give 2, not 1.
        self.assertNotEqual(report["duplicate_raw_value_rows"], 1)
        # Documented consequence: whitespace-only cells are missing, not duplicates.
        self.assertEqual(set(blockers), {"APPID_MISSING"})
        self.assertNotIn("APPID_DUPLICATE", blockers)

    def test_c03_audit_appid_strip_duplicate_blocker(self):
        frame = pd.DataFrame({"appid": ["1", " 1 "]})
        report, blockers = CANDIDATE.audit_appid(frame)
        self.assertIsInstance(report, dict)
        self.assertIsInstance(blockers, dict)
        self.assertEqual(report["duplicate_raw_value_rows"], 0)
        self.assertEqual(report["duplicate_after_strip_rows"], 2)
        self.assertEqual(set(blockers), {"APPID_DUPLICATE"})
        self.assertNotIn("APPID_MISSING", blockers)
        self.assertNotIn("APPID_ILLEGAL", blockers)

    def test_c04_audit_numeric_overflow_is_not_finite(self):
        report = CANDIDATE.audit_numeric(pd.Series(["1e309"]), "required_age",
                                         CONFIG)
        # Aggregation report only: not a (report, blockers) pair.
        self.assertIsInstance(report, dict)
        self.assertEqual(report["rows_in_scope"], 1)
        counts = report["class_counts"]
        self.assertEqual(counts["out_of_range_after_conversion"], 1)
        self.assertEqual(counts["finite_integer"], 0)
        self.assertEqual(counts["finite_decimal"], 0)
        self.assertIsNone(report["accepted_value_min"])
        self.assertIsNone(report["accepted_value_max"])

    def test_c05_audit_entity_field_inline_missing(self):
        case = _case("C-05")
        synthetic = case["synthetic_input"]
        columns = tuple(synthetic["columns_to_parameterize"])
        values = tuple(synthetic["values_to_parameterize"])
        self.assertEqual(columns, ("developer", "publisher"))
        self.assertEqual(set(values), {"A;unknown", "A;unknown;NULL"})
        self.assertEqual(len(columns) * len(values),
                         synthetic["calls_per_case"])
        for column in columns:
            for value in values:
                with self.subTest(column=column, value=value):
                    frame, mask = self._component_frame(column, value)
                    self.assertEqual(int(mask.sum()), 1)
                    report = CANDIDATE.audit_entity_field(frame, column, mask,
                                                          CONFIG)
                    self.assertIsInstance(report, dict)
                    self.assertEqual(report["rows_in_scope"], 1)
                    self.assertEqual(report["rows_with_inline_missing_token"], 1)
                    self.assertEqual(report["entity_total_after_dedup"], 1)
                    self.assertEqual(report["rows_resolving_to_one_entity"], 1)
                    self.assertEqual(
                        report["rows_with_inline_duplicate_entities"], 0)
                    self.assertEqual(
                        report["rows_with_whitespace_padded_entity_tokens"], 0)
        # A merged call must not be read as a per-row report: 2 rows, 2 flags.
        for column in columns:
            with self.subTest(column=column, merged=True):
                frame = pd.DataFrame({column: list(values)})
                mask = pd.Series([True, True], index=frame.index)
                report = CANDIDATE.audit_entity_field(frame, column, mask,
                                                      CONFIG)
                self.assertEqual(report["rows_in_scope"], 2)
                self.assertEqual(report["rows_with_inline_missing_token"], 2)
                self.assertEqual(report["entity_total_after_dedup"], 2)

    def test_c06_audit_entity_field_empty_token_and_dedup(self):
        case = _case("C-06")
        synthetic = case["synthetic_input"]
        columns = tuple(synthetic["columns_to_parameterize"])
        values = tuple(synthetic["values_to_parameterize"])
        self.assertEqual(columns, ("developer", "publisher"))
        self.assertEqual(set(values), {"A;;B", "A;A;B"})
        self.assertEqual(len(columns) * len(values),
                         synthetic["calls_per_case"])
        duplicate_flag = {"A;;B": 0, "A;A;B": 1}
        for column in columns:
            for value in values:
                with self.subTest(column=column, value=value):
                    frame, mask = self._component_frame(column, value)
                    report = CANDIDATE.audit_entity_field(frame, column, mask,
                                                          CONFIG)
                    self.assertEqual(report["rows_in_scope"], 1)
                    self.assertEqual(report["entity_total_after_dedup"], 2)
                    self.assertEqual(
                        report["rows_resolving_to_multiple_entities"], 1)
                    # Checked separately: inline_missing == 0 does not imply
                    # the whitespace-padding count is 0.
                    self.assertEqual(
                        report["rows_with_inline_missing_token"], 0)
                    self.assertEqual(
                        report["rows_with_whitespace_padded_entity_tokens"], 0)
                    self.assertEqual(
                        report["rows_with_inline_duplicate_entities"],
                        duplicate_flag[value])

    # ------------------------------------------------------------------
    # main-flow cases C-07 .. C-10
    # ------------------------------------------------------------------
    def _assert_cli_result(self, completed, expected_returncode):
        self.assertEqual(completed.returncode, expected_returncode,
                         "unexpected exit code " + str(completed.returncode)
                         + "; stderr tail: " + completed.stderr[-1500:])
        self.assertNotEqual(completed.stdout.strip(), "",
                            "stdout carried no JSON object")
        self.assertNotEqual(completed.stderr.strip(), "",
                            "stderr carried no diagnostics")
        report = _parse_stdout(completed.stdout)
        # The in-JSON exit code must agree with the real process exit code.
        self.assertEqual(report["exit_code"], completed.returncode)
        return report

    def _assert_untouched(self, directory, before):
        after = _snapshot(directory)
        self.assertEqual(sorted(after), sorted(before),
                         "candidate created or removed files in the synthetic "
                         "input directory")
        self.assertEqual(after, before,
                         "candidate rewrote a synthetic input file")

    def _assert_coverage_partition(self, report, forbidden):
        checks = report["checks"]
        completed_records = checks["checks_completed_this_run"]
        not_run_records = checks["checks_not_run_this_run"]
        for record in list(completed_records) + list(not_run_records):
            self.assertIsInstance(record, dict)
            self.assertIn("stage", record)
        completed = _stages(completed_records)
        not_run = _stages(not_run_records)
        self.assertEqual(len(completed_records), len(completed),
                         "duplicate stage records in checks_completed_this_run")
        self.assertEqual(len(not_run_records), len(not_run),
                         "duplicate stage records in checks_not_run_this_run")
        self.assertFalse(completed & not_run,
                         "completed and not-run stages must be disjoint")
        self.assertEqual(completed | not_run, set(PLANNED_STAGES))
        self.assertEqual(len(completed) + len(not_run), 13)
        for stage in forbidden:
            self.assertNotIn(stage, completed,
                             stage + " must not be marked completed here")

    def test_c07_main_flow_date_window_utc_nat_and_2018_isolation(self):
        case = _case("C-07")
        rows = case["synthetic_input"]["rows"]
        self.assertEqual(len(rows), 6)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = _write_csv(directory, "c07.csv", REQUIRED_COLUMNS, rows)
            before = _snapshot(directory)
            completed = _run_cli(csv_path)
            report = self._assert_cli_result(completed, 4)
            self._assert_untouched(directory, before)

        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["exit_code"], 4)
        self.assertTrue(report["checks"]["pending_human_decisions"])

        date_audit = report["date_audit"]
        self.assertEqual(date_audit["nat_rows"], 1)
        self.assertEqual(date_audit["fit_window_rows_le_train_max_year"], 1)
        self.assertEqual(date_audit["selection_year_rows"], 2)
        self.assertEqual(date_audit["test_year_rows"], 1)
        self.assertEqual(date_audit["excluded_year_rows"], 1)

        scope = report["field_audit_scope"]
        self.assertEqual(scope["rows_in_scope"], 3)
        self.assertEqual(scope["test_year_rows_excluded"], 1)
        self.assertIs(scope["used_to_select_preprocessing"], False)

        english = report["field_audit"]["english"]
        self.assertEqual(english["rows_in_scope"], 3)
        self.assertEqual(english["legal_one"], 3)
        self.assertEqual(english["illegal_non_empty_value"], 0)

        required_age = report["field_audit"]["required_age"]
        self.assertEqual(required_age["rows_in_scope"], 3)
        self.assertEqual(required_age["class_counts"]["finite_integer"], 3)
        self.assertEqual(
            required_age["class_counts"]["out_of_range_after_conversion"], 0)
        self.assertEqual(required_age["class_counts"]["other_unparseable"], 0)

        # The 2018 faults stayed outside every aggregate.
        self.assertFalse(report.get("blocking_findings"))
        findings = report.get("blocking_findings") or {}
        self.assertNotIn("ENGLISH_ILLEGAL_VALUE", findings)
        self.assertNotIn("REQUIRED_AGE_PARSE_FAILURE", findings)

        # UTC crossing and NaT, observed through the candidate's own date entry
        # point rather than through a per-row identifier in the aggregate.
        frame = pd.DataFrame(rows, columns=list(REQUIRED_COLUMNS))
        self.assertEqual(len(frame), 6)
        self.assertEqual(len(frame.columns), 9)
        parsed = CANDIDATE.parse_dates(frame, CONFIG)
        self.assertEqual(str(parsed.dt.tz), "UTC")
        self.assertEqual(parsed.iloc[0],
                         pd.Timestamp("2017-01-01T04:30:00+00:00"))
        self.assertEqual(int(parsed.iloc[0].year), 2017)
        self.assertTrue(pd.isna(parsed.iloc[1]))
        self.assertEqual(int(parsed.isna().sum()), 1)
        self.assertEqual(int(parsed.notna().sum()), 5)

    def test_c08_main_flow_read_failure_paths(self):
        case = _case("C-08")
        scenarios = case["synthetic_input"]["scenarios"]
        self.assertEqual([item["scenario_id"] for item in scenarios],
                         ["C-08a", "C-08b"])

        with tempfile.TemporaryDirectory() as directory:
            # C-08a: header lacks the other seven required columns.
            short_columns = ("appid", "release_date")
            short_rows = [{"appid": "1", "release_date": "2016-06-01"}]
            short_csv = _write_csv(directory, "c08a.csv", short_columns,
                                   short_rows)
            before = _snapshot(directory)
            completed = _run_cli(short_csv)
            report_a = self._assert_cli_result(completed, 3)
            self._assert_untouched(directory, before)

            self.assertEqual(report_a["status"], "BLOCKED")
            self.assertEqual(report_a["verdict"], "PRECHECK_BLOCKED")
            self.assertIn("REQUIRED_COLUMNS_MISSING",
                          report_a.get("blocking_findings") or {})
            # Explicitly reported, never padded: no frame and no field audit.
            self.assertNotIn("input", report_a)
            self.assertNotIn("field_audit", report_a)
            self._assert_coverage_partition(report_a, POST_READ_STAGES)
            self.assertEqual(
                _stages(report_a["checks"]["checks_completed_this_run"]),
                {"input_exists", "config", "environment", "header"})

            # C-08b: complete legal 9-column header, illegal UTF-8 bytes in the
            # body, encoding declared explicitly as utf-8.
            header = ",".join(REQUIRED_COLUMNS).encode("ascii") + b"\n"
            body = (b"1,2016-06-01,1,A,P,windows,0,"
                    + b"\xff\xfe" + b"Single-player,Action\n")
            bad_csv = Path(directory) / "c08b.csv"
            bad_csv.write_bytes(header + body)
            before = _snapshot(directory)
            completed = _run_cli(bad_csv, encoding="utf-8")
            report_b = self._assert_cli_result(completed, 1)
            self._assert_untouched(directory, before)

            self.assertEqual(report_b["status"], "BLOCKED")
            self.assertEqual(report_b["verdict"], "PRECHECK_BLOCKED")
            findings = report_b.get("blocking_findings") or {}
            self.assertEqual(len(findings), 1)
            self.assertTrue(
                set(findings) <= {"HEADER_ENCODING_FAILURE",
                                  "BODY_ENCODING_FAILURE"},
                "unexpected encoding finding: " + repr(sorted(findings)))
            # A decode failure must never become an empty-data success.
            self.assertNotIn("input", report_b)
            self.assertNotIn("field_audit", report_b)
            self._assert_coverage_partition(report_b, POST_READ_STAGES)

    def test_c09_restricted_read_usecols_and_read_parameters(self):
        case = _case("C-09")
        synthetic = case["synthetic_input"]
        file_columns = list(synthetic["synthetic_csv_columns"])
        required_usecols = list(synthetic["required_usecols"])
        extra_values = dict(synthetic["extra_column_values"])
        self.assertEqual(required_usecols, list(REQUIRED_COLUMNS))
        self.assertEqual(len(file_columns), 11)
        extra_names = [name for name in file_columns
                       if name not in required_usecols]
        self.assertEqual(set(extra_names), set(extra_values))
        self.assertEqual(len(extra_names), 2)

        rows = [dict(row, **extra_values) for row in _baseline_rows()]
        with tempfile.TemporaryDirectory() as directory:
            csv_path = _write_csv(directory, "c09.csv", file_columns, rows)
            before = _snapshot(directory)

            recorded = []
            original_read_csv = pd.read_csv

            def recording_read_csv(*args, **kwargs):
                # Call the saved original and record the genuine result columns.
                result = original_read_csv(*args, **kwargs)
                recorded.append({
                    "args": args,
                    "kwargs": dict(kwargs),
                    "is_dataframe": isinstance(result, pd.DataFrame),
                    "columns": list(result.columns),
                })
                return result

            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(pd, "read_csv", recording_read_csv):
                with contextlib.redirect_stdout(out), \
                        contextlib.redirect_stderr(err):
                    rc = CANDIDATE.main(["--input-main", str(csv_path),
                                         "--tree", "rf"])
            self._assert_untouched(directory, before)

        self.assertNotEqual(recorded, [],
                            "the candidate never called the real pd.read_csv")
        self.assertNotEqual(err.getvalue().strip(), "",
                            "stderr carried no diagnostics")
        report = _parse_stdout(out.getvalue())
        self.assertEqual(rc, report["exit_code"])
        self.assertEqual(rc, 4)
        self.assertTrue(report["checks"]["pending_human_decisions"])

        for index, call in enumerate(recorded):
            kwargs = call["kwargs"]
            with self.subTest(read_csv_call=index):
                # Refuse "read the whole table, then drop columns".
                self.assertIn("usecols", kwargs,
                              "unrestricted read: usecols was not passed")
                self.assertEqual(len(kwargs["usecols"]), 9)
                self.assertEqual(set(kwargs["usecols"]),
                                 set(required_usecols))
                self.assertIs(kwargs["dtype"], str)
                self.assertIs(kwargs["keep_default_na"], False)
                self.assertIs(kwargs["na_filter"], False)
            with self.subTest(read_csv_result=index):
                self.assertTrue(call["is_dataframe"])
                self.assertEqual(len(call["columns"]), 9)
                self.assertEqual(set(call["columns"]), set(required_usecols))
                # The sentinel result/label columns were never selected; only
                # column names are inspected, never their values.
                self.assertFalse(set(call["columns"]) & set(extra_names))

    def test_c10_clean_baseline_pending_items_not_a_blocker(self):
        rows = _baseline_rows()
        self.assertEqual(len(rows), 3)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = _write_csv(directory, "c10.csv", REQUIRED_COLUMNS, rows)
            before = _snapshot(directory)
            completed = _run_cli(csv_path)
            report = self._assert_cli_result(completed, 4)
            self._assert_untouched(directory, before)

        # exit 4 means "completed with open items": neither a data blocker nor
        # a clean run, and not a full-pipeline GO.
        self.assertEqual(report["exit_code"], 4)
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["verdict"],
                         "NO_DATA_BLOCKER_WITH_OPEN_ITEMS")
        self.assertNotEqual(report["verdict"],
                            "NO_DATA_BLOCKER_NO_OPEN_ITEMS")
        self.assertFalse(report.get("blocking_findings"))
        self.assertEqual(report["schema"], "stage0_precheck.h04_r4")
        self.assertEqual(report["baseline_schema"],
                         "stage0_precheck.h04_gpt_r3")

        self.assertEqual(
            _stages(report["checks"]["checks_completed_this_run"]),
            set(PLANNED_STAGES))
        self.assertEqual(
            len(report["checks"]["checks_completed_this_run"]), 13)
        self.assertEqual(report["checks"]["checks_not_run_this_run"], [])
        self.assertTrue(report["checks"]["pending_human_decisions"])
        self._assert_coverage_partition(report, ())

        self.assertEqual(report["field_audit_scope"]["rows_in_scope"], 2)
        self.assertIs(
            report["field_audit_scope"]["used_to_select_preprocessing"], False)

        # --tree rf is an explicit precheck branch, not a frozen tree family.
        self.assertEqual(report["run"]["tree_branch_requested"], "rf")
        self.assertIs(report["run"]["tree_family_frozen_by_this_run"], False)

        # No formal split, X or y is produced by this run.
        for guarded in ("X", "y", "split"):
            self.assertNotIn(guarded, report)

        # Physical no-write evidence is _assert_untouched above; the flag is
        # self-reported and is asserted only as an additional claim.
        self.assertIs(report["checks"]["scope_guards"]["file_written"], False)


if __name__ == "__main__":
    unittest.main()
