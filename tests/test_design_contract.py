"""Critical frozen-design boundaries, independent of the Steam raw files."""

import unittest
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

import config
from scripts.validate_steam_data import calendar_features, history_features, prepare_analytical


class DesignContractTests(unittest.TestCase):
    def test_linear_inclusive_small_cohorts_and_excluded_year(self):
        raw = pd.DataFrame({
            "release_date": ["1997-01-01", "2018-01-01", "2018-02-01", "2018-03-01", "2019-01-01", "bad-date"],
            "positive_ratings": [7, 1, 10, 10, 999, 1], "negative_ratings": [0] * 6,
        })
        result = prepare_analytical(raw)
        self.assertEqual(result.loc[:3, "hit_reviews"].tolist(), [1, 0, 1, 1])
        self.assertTrue(result.loc[4:, "hit_reviews"].isna().all())
        self.assertEqual(result["split"].tolist(), ["train", "test", "test", "test", "excluded", "unknown"])
        reversed_result = prepare_analytical(raw.iloc[::-1]).sort_index()
        pd.testing.assert_series_equal(result["hit_reviews"], reversed_result["hit_reviews"])
        # Linear q90 for two observations lies between them; "lower" would label both.
        pair = raw.iloc[:2].copy()
        pair["release_date"] = "2001-01-01"
        self.assertEqual(prepare_analytical(pair)["hit_reviews"].tolist(), [1, 0])

    def test_utc_cohort_boundary_and_calendar_cycles(self):
        dates = pd.Series(["2018-12-31T23:30:00-01:00", "2018-01-01", "invalid"])
        raw = pd.DataFrame({"release_date": dates, "positive_ratings": [1, 2, 3], "negative_ratings": [0, 0, 0]})
        result = prepare_analytical(raw)
        self.assertEqual(str(result["release_date_utc"].dt.tz), "UTC")
        self.assertEqual(result.loc[0, "release_year"], 2019)
        self.assertTrue(pd.isna(result.loc[0, "hit_reviews"]))
        calendar = calendar_features(dates)
        self.assertEqual(calendar.loc[1, "release_day_of_week"], 0)  # 2018-01-01 was Monday.
        self.assertAlmostEqual(calendar.loc[1, "release_month_sin"], 0)
        self.assertAlmostEqual(calendar.loc[1, "release_month_cos"], 1)
        self.assertAlmostEqual(calendar.loc[1, "release_day_of_week_cos"], 1)
        self.assertTrue(calendar.loc[2].isna().all())

    def test_history_union_strict_year_and_missing_defaults(self):
        frame = pd.DataFrame({
            "appid": range(1, 8),
            "release_year": [2015, 2015, 2016, 2016, 2016, 2016, 2017],
            "developer": ["A;B;A", "B", "B;C", "A;B", "C", "  ", "A;C"],
            "publisher": ["P;Q", "Q", "P", "P;Q", None, "Unknown", "P"],
            "hit_reviews": [1, 0, 1, 0, 1, 1, 1],
        })
        result = history_features(frame)
        self.assertAlmostEqual(result.loc[3, "dev_prior_count"], np.log1p(2))
        self.assertAlmostEqual(result.loc[3, "dev_prior_hit_rate"], (1 + 10 * .10) / (2 + 10))
        self.assertAlmostEqual(result.loc[3, "pub_prior_count"], np.log1p(2))
        # C's 2016 records, including a preceding row, cannot inform another 2016 release.
        self.assertEqual(result.loc[4, "dev_prior_count"], 0)
        self.assertEqual(result.loc[4, "dev_prior_hit_rate"], .10)
        self.assertEqual(result.loc[5, "dev_prior_count"], 0)
        self.assertEqual(result.loc[5, "pub_prior_count"], 0)
        # A|C in 2017 pools four distinct prior games, not entity memberships.
        self.assertAlmostEqual(result.loc[6, "dev_prior_count"], np.log1p(4))
        self.assertAlmostEqual(result.loc[6, "dev_prior_hit_rate"], (3 + 1) / 14)
        pd.testing.assert_frame_equal(result, history_features(frame.iloc[::-1]).sort_index())

    def test_whitelist_blocks_tags_snapshot_target_and_metadata(self):
        self.assertTrue(config.assert_primary_feature_columns(["genres", "dev_prior_hit_rate", "release_month_sin"]))
        for column in ("steamspy_tags", "tag_count", "price", "achievements", "is_free_true", "hit_reviews", "release_year", "appid", "renamed_unknown_outcome"):
            with self.subTest(column=column), self.assertRaises(ValueError):
                config.assert_primary_feature_columns(["genres", column])

    def test_cli_refuses_existing_output_before_reading_input(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "validate_steam_data.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.json"
            output.write_text("preserved", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script), "--data-dir", str(Path(directory) / "absent"), "--output", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserved")


if __name__ == "__main__":
    unittest.main()
