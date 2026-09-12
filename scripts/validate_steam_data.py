"""Reproducible acceptance checks for the 6102 Steam dataset.

The script performs read-only checks on the raw CSV files and writes a compact
JSON snapshot only when ``--output`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EXPECTED_FILES = {
    "steam.csv": "783087562C9BAB27FAF7C4C1C8040269489AB2FC2054549971BE01EB6C007F99",
    "steam_description_data.csv": "560FCEF21B52DFBB387C9E9D3A4FFD4505472B835E0BCA8F3BF03206B09BBD28",
    "steam_media_data.csv": "BA754CDF6589B2134B7F104F7AB95AA51FFDB466D020B81FD29D47196108D41F",
    "steam_requirements_data.csv": "5909E55018ADB52436A8700366EB58DBFE53B8DC2876437BD85901C7FE760637",
    "steam_support_info.csv": "F271C3FD19011ED1566960A0F5F18EEFBBE872C88282A5D3F93085EF57BAA33F",
    "steamspy_tag_data.csv": "98B8FB0120177F7292755119BCCBDDE6387A9C0C90979593DD0D6C0DC791B183",
}

EXPECTED_MAIN_COLUMNS = [
    "appid",
    "name",
    "release_date",
    "english",
    "developer",
    "publisher",
    "platforms",
    "required_age",
    "categories",
    "genres",
    "steamspy_tags",
    "achievements",
    "positive_ratings",
    "negative_ratings",
    "average_playtime",
    "median_playtime",
    "owners",
    "price",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def to_native(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_native(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def tie_aware_top_fraction(y: pd.Series, score: pd.Series, fraction: float) -> dict[str, float | int]:
    """Expected top-fraction result when observations tie at the cutoff."""
    y_array = y.to_numpy(dtype=int)
    score_array = score.to_numpy(dtype=float)
    top_n = math.ceil(len(y_array) * fraction)
    cutoff = np.sort(score_array)[-top_n]
    above = score_array > cutoff
    tied = score_array == cutoff
    slots_from_tie = top_n - int(above.sum())
    expected_hits = float(y_array[above].sum())
    expected_hits += slots_from_tie * float(y_array[tied].mean())
    selected_rate = expected_hits / top_n
    base_rate = float(y_array.mean())
    return {
        "top_n": top_n,
        "cutoff": float(cutoff),
        "strictly_above_cutoff": int(above.sum()),
        "tied_at_cutoff": int(tied.sum()),
        "slots_from_tie": slots_from_tie,
        "expected_selected_hit_rate": selected_rate,
        "expected_lift": selected_rate / base_rate,
    }


def rank_auc(y: pd.Series, score: pd.Series) -> float:
    """ROC-AUC from average ranks, so score ties receive half credit."""
    y_array = y.to_numpy(dtype=int)
    ranks = score.rank(method="average").to_numpy(dtype=float)
    positives = int(y_array.sum())
    negatives = len(y_array) - positives
    return float(
        (ranks[y_array == 1].sum() - positives * (positives + 1) / 2)
        / (positives * negatives)
    )


def grouped_average_precision(y: pd.Series, score: pd.Series) -> float:
    """Tie-aware stepwise area under the precision-recall curve."""
    frame = pd.DataFrame({"y": y.to_numpy(dtype=int), "score": score.to_numpy(dtype=float)})
    grouped = frame.groupby("score", sort=False)["y"].agg(["sum", "count"]).sort_index(ascending=False)
    true_positive = grouped["sum"].cumsum()
    selected = grouped["count"].cumsum()
    recall = true_positive / int(frame["y"].sum())
    precision = true_positive / selected
    delta_recall = recall.diff().fillna(recall.iloc[0])
    return float((delta_recall * precision).sum())


def history_score(history: pd.DataFrame, future: pd.DataFrame, column: str, alpha: float = 20.0) -> pd.Series:
    """Bayesian-smoothed prior hit rate using historical records only."""
    base_rate = float(history["hit_reviews"].mean())
    aggregate = history.groupby(column, dropna=False)["hit_reviews"].agg(["sum", "count"])
    mapping = (aggregate["sum"] + alpha * base_rate) / (aggregate["count"] + alpha)
    return future[column].map(mapping).fillna(base_rate)


def audit(data_dir: Path) -> dict[str, Any]:
    missing_files = [name for name in EXPECTED_FILES if not (data_dir / name).is_file()]
    if missing_files:
        raise FileNotFoundError(f"Missing required files: {', '.join(missing_files)}")

    files: dict[str, Any] = {}
    tables: dict[str, pd.DataFrame] = {}
    for name, expected_hash in EXPECTED_FILES.items():
        path = data_dir / name
        actual_hash = sha256(path)
        frame = pd.read_csv(path, low_memory=False)
        tables[name] = frame
        key = "appid" if "appid" in frame.columns else "steam_appid"
        files[name] = {
            "bytes": path.stat().st_size,
            "sha256": actual_hash,
            "hash_matches_expected": actual_hash == expected_hash,
            "rows": len(frame),
            "columns": len(frame.columns),
            "exact_duplicate_rows": int(frame.duplicated().sum()),
            "key": key,
            "key_nulls": int(frame[key].isna().sum()),
            "key_duplicates": int(frame[key].duplicated().sum()),
        }

    main = tables["steam.csv"].copy()
    main_ids = set(main["appid"])
    auxiliary_coverage: dict[str, Any] = {}
    for name, frame in tables.items():
        if name == "steam.csv":
            continue
        key = "appid" if "appid" in frame.columns else "steam_appid"
        auxiliary_ids = set(frame[key])
        auxiliary_coverage[name] = {
            "main_rows_covered": len(main_ids & auxiliary_ids),
            "main_coverage_rate": len(main_ids & auxiliary_ids) / len(main_ids),
            "extra_auxiliary_ids": len(auxiliary_ids - main_ids),
            "missing_main_ids": len(main_ids - auxiliary_ids),
        }

    dates = pd.to_datetime(main["release_date"], errors="coerce")
    owners_parts = main["owners"].astype(str).str.extract(r"^\s*([0-9,]+)\s*-\s*([0-9,]+)\s*$")
    owner_lower = pd.to_numeric(owners_parts[0].str.replace(",", ""), errors="coerce")
    owner_upper = pd.to_numeric(owners_parts[1].str.replace(",", ""), errors="coerce")
    owner_midpoint = (owner_lower + owner_upper) / 2
    reviews = main["positive_ratings"] + main["negative_ratings"]

    analytical = main.assign(
        release_year=dates.dt.year,
        total_ratings=reviews,
        owner_midpoint=owner_midpoint,
    )
    owner_q90 = analytical.groupby("release_year")["owner_midpoint"].transform(lambda values: values.quantile(0.9))
    analytical["hit_owner_inclusive"] = analytical["owner_midpoint"].ge(owner_q90)
    rating_q90 = analytical.groupby("release_year")["total_ratings"].transform(lambda values: values.quantile(0.9))
    analytical["hit_reviews"] = analytical["total_ratings"].ge(rating_q90).astype(int)

    through_2018 = analytical[analytical["release_year"].le(2018)].copy()
    splits: dict[str, Any] = {}
    for name, mask in {
        "train_through_2016": through_2018["release_year"].le(2016),
        "validation_2017": through_2018["release_year"].eq(2017),
        "test_2018": through_2018["release_year"].eq(2018),
    }.items():
        split = through_2018[mask]
        splits[name] = {
            "rows": len(split),
            "positive_rate_review_top_decile": float(split["hit_reviews"].mean()),
            "positive_rate_owner_q90_inclusive": float(split["hit_owner_inclusive"].mean()),
        }

    rule_baseline: dict[str, Any] = {}
    for evaluation_year in (2017, 2018):
        history = through_2018[through_2018["release_year"].lt(evaluation_year)]
        future = through_2018[through_2018["release_year"].eq(evaluation_year)]
        developer_score = history_score(history, future, "developer")
        publisher_score = history_score(history, future, "publisher")
        score = (developer_score + publisher_score) / 2
        rule_baseline[str(evaluation_year)] = {
            "rows": len(future),
            "positive_rate": float(future["hit_reviews"].mean()),
            "roc_auc": rank_auc(future["hit_reviews"], score),
            "average_precision": grouped_average_precision(future["hit_reviews"], score),
            "top_10_percent": tie_aware_top_fraction(future["hit_reviews"], score, 0.10),
            "unseen_developer_rate": float((~future["developer"].isin(history["developer"])).mean()),
            "unseen_publisher_rate": float((~future["publisher"].isin(history["publisher"])).mean()),
        }

    structural_checks = {
        "all_hashes_match": all(item["hash_matches_expected"] for item in files.values()),
        "main_schema_matches": list(main.columns) == EXPECTED_MAIN_COLUMNS,
        "main_row_count_is_27075": len(main) == 27075,
        "main_appid_complete_unique": main["appid"].notna().all() and not main["appid"].duplicated().any(),
        "main_has_no_exact_duplicate_rows": not main.duplicated().any(),
        "all_release_dates_parse": dates.notna().all(),
        "all_owner_ranges_parse": owner_lower.notna().all() and owner_upper.notna().all(),
        "all_owner_ranges_have_valid_bounds": bool((owner_lower < owner_upper).all()),
        "all_rating_counts_nonnegative": bool(main[["positive_ratings", "negative_ratings"]].ge(0).all().all()),
        "all_games_have_at_least_one_rating": bool(reviews.gt(0).all()),
    }

    return to_native(
        {
            "verdict": {
                "file_integrity": "PASS" if all(structural_checks.values()) else "FAIL",
                "analytical_acceptance": "CONDITIONAL_GO",
                "reason": (
                    "Use release-year top-decile total ratings as the primary popularity label, "
                    "exclude 2019, enforce chronological validation, and exclude post-release outcomes/tags."
                ),
            },
            "structural_checks": structural_checks,
            "files": files,
            "main_table": {
                "rows": len(main),
                "columns": len(main.columns),
                "missing_values": {
                    column: int(count)
                    for column, count in main.isna().sum().items()
                    if int(count) > 0
                },
                "release_date_min": dates.min(),
                "release_date_max": dates.max(),
                "release_year_counts": dates.dt.year.value_counts().sort_index().to_dict(),
                "owner_interval_count": int(main["owners"].nunique()),
                "owner_q90_inclusive_positive_rate_all_years": float(analytical["hit_owner_inclusive"].mean()),
                "owner_q90_inclusive_positive_rate_2019": float(
                    analytical.loc[analytical["release_year"].eq(2019), "hit_owner_inclusive"].mean()
                ),
                "review_top_decile_positive_rate_through_2018": float(through_2018["hit_reviews"].mean()),
                "owner_midpoint_review_count_spearman": float(
                    analytical["owner_midpoint"].rank().corr(analytical["total_ratings"].rank())
                ),
            },
            "auxiliary_coverage": auxiliary_coverage,
            "recommended_time_splits": splits,
            "time_safe_rule_baseline": rule_baseline,
            "feature_policy": {
                "primary_features": [
                    "release month/quarter",
                    "english",
                    "developer/publisher encoded only from prior releases",
                    "platforms",
                    "required_age",
                    "categories",
                    "genres",
                ],
                "sensitivity_only_snapshot_features": ["price", "achievements", "descriptions/requirements/media"],
                "forbidden_predictors": [
                    "positive_ratings",
                    "negative_ratings",
                    "owners",
                    "average_playtime",
                    "median_playtime",
                    "steamspy_tags",
                    "steamspy_tag_data.csv vote counts",
                ],
            },
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "raw" / "steam_store_games",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    result = audit(args.data_dir)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
