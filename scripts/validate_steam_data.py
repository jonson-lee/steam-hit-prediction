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
import sys
from typing import Any

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as design


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
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {str(key): to_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_native(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
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
    if not len(y_array) or not 0 < fraction <= 1:
        raise ValueError("Top-fraction evaluation requires rows and 0 < fraction <= 1")
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
        "expected_precision": selected_rate,
        "expected_recall": expected_hits / int(y_array.sum()) if y_array.sum() else float("nan"),
        "expected_lift": selected_rate / base_rate if base_rate else float("nan"),
    }


def rank_auc(y: pd.Series, score: pd.Series) -> float:
    """ROC-AUC from average ranks, so score ties receive half credit."""
    y_array = y.to_numpy(dtype=int)
    ranks = score.rank(method="average").to_numpy(dtype=float)
    positives = int(y_array.sum())
    negatives = len(y_array) - positives
    if not positives or not negatives:
        return float("nan")
    return float(
        (ranks[y_array == 1].sum() - positives * (positives + 1) / 2)
        / (positives * negatives)
    )


def grouped_average_precision(y: pd.Series, score: pd.Series) -> float:
    """Tie-aware stepwise area under the precision-recall curve."""
    frame = pd.DataFrame({"y": y.to_numpy(dtype=int), "score": score.to_numpy(dtype=float)})
    if frame.empty or not frame["y"].sum():
        return float("nan")
    grouped = frame.groupby("score", sort=False)["y"].agg(["sum", "count"]).sort_index(ascending=False)
    true_positive = grouped["sum"].cumsum()
    selected = grouped["count"].cumsum()
    recall = true_positive / int(frame["y"].sum())
    precision = true_positive / selected
    delta_recall = recall.diff().fillna(recall.iloc[0])
    return float((delta_recall * precision).sum())


def parse_release_dates(values: pd.Series) -> pd.Series:
    """D-020: explicit UTC conversion; malformed values remain visible as NaT."""
    return pd.to_datetime(
        values, errors=design.RELEASE_DATE_ERRORS, utc=design.RELEASE_DATE_UTC,
        format=design.RELEASE_DATE_FORMAT,
    )


def calendar_features(release_dates: pd.Series) -> pd.DataFrame:
    """D-018: calendar inputs and cycles, with January=0 angle and Monday=0."""
    dates = parse_release_dates(release_dates)
    month = dates.dt.month.astype("Int64")
    day = dates.dt.dayofweek.astype("Int64")
    month_angle = 2 * np.pi * (month.astype(float) - design.MONTH_CYCLE_ORIGIN) / design.MONTH_CYCLE_PERIOD
    day_angle = 2 * np.pi * (day.astype(float) - design.DAY_OF_WEEK_CYCLE_ORIGIN) / design.DAY_OF_WEEK_CYCLE_PERIOD
    return pd.DataFrame({
        "release_month": month,
        "release_quarter": dates.dt.quarter.astype("Int64"),
        "release_day_of_week": day,
        "release_month_sin": np.sin(month_angle), "release_month_cos": np.cos(month_angle),
        "release_day_of_week_sin": np.sin(day_angle), "release_day_of_week_cos": np.cos(day_angle),
    }, index=release_dates.index)


def prepare_analytical(main: pd.DataFrame) -> pd.DataFrame:
    """Produce the frozen labels/cohorts without dropping or mutating raw rows."""
    analytical = main.copy()
    dates = parse_release_dates(main["release_date"])
    analytical["release_date_utc"] = dates
    analytical["release_year"] = dates.dt.year.astype("Int64")
    for column, values in calendar_features(main["release_date"]).items():
        analytical[column] = values
    analytical["total_ratings"] = main["positive_ratings"] + main["negative_ratings"]
    eligible = dates.notna() & ~analytical["release_year"].isin(design.EXCLUDED_RELEASE_YEARS)
    analytical[design.TARGET_COLUMN] = pd.Series(pd.NA, index=main.index, dtype="Int8")
    cutoffs = analytical.loc[eligible].groupby("release_year")["total_ratings"].transform(
        lambda values: values.quantile(design.TARGET_QUANTILE, interpolation=design.TARGET_INTERPOLATION)
    )
    target_values = analytical.loc[eligible, "total_ratings"]
    target = target_values.ge(cutoffs) if design.TARGET_INCLUSIVE else target_values.gt(cutoffs)
    analytical.loc[eligible, design.TARGET_COLUMN] = target.astype("Int8")
    analytical["split"] = "unknown"
    analytical.loc[analytical["release_year"].isin(design.EXCLUDED_RELEASE_YEARS), "split"] = "excluded"
    for name, mask in (
        ("train", analytical["release_year"].le(design.TRAIN_MAX_YEAR)),
        ("validation", analytical["release_year"].eq(design.VALIDATION_YEAR)),
        ("test", analytical["release_year"].eq(design.TEST_YEAR)),
    ):
        analytical.loc[mask.fillna(False) & eligible, "split"] = name
    return analytical


def split_entities(value: Any) -> tuple[str, ...]:
    """Split D-023 memberships, stripping blanks and repeated entities."""
    if pd.isna(value):
        return ()
    entities = (item.strip() for item in str(value).split(design.ENTITY_DELIMITER))
    return tuple(dict.fromkeys(item for item in entities if item and item.lower() not in design.ENTITY_MISSING_TOKENS))


def history_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Walk forward by year, pooling the union of each entity's earlier games.

    A prior game shared by multiple listed entities counts once. The four output
    counts are already log1p transformed; rates use the fixed configured prior.
    Same-year games are inserted only after every game in that year is encoded.
    """
    years = pd.to_numeric(frame["release_year"], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    labels = pd.to_numeric(frame[design.TARGET_COLUMN], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if not np.isin(labels[np.isfinite(labels)], [0, 1]).all():
        raise ValueError("Historical targets must be binary or missing")
    if "appid" in frame and frame["appid"].duplicated().any():
        raise ValueError("Historical encoding requires one row per appid")
    output = {}
    for column, prefix in (("developer", "dev"), ("publisher", "pub")):
        memberships = [split_entities(value) for value in frame[column]]
        counts = np.zeros(len(frame), dtype=float)
        rates = np.full(len(frame), design.HISTORY_PRIOR_MEAN, dtype=float)
        prior_games: dict[str, set[int]] = {}
        for year in sorted(np.unique(years[np.isfinite(years)])):
            positions = np.flatnonzero(years == year)
            for position in positions:
                pooled: set[int] = set()
                for entity in memberships[position]:
                    pooled.update(prior_games.get(entity, ()))
                count = len(pooled)
                hits = float(labels[list(pooled)].sum()) if pooled else 0.0
                counts[position] = np.log1p(count)
                rates[position] = (hits + design.HISTORY_ALPHA * design.HISTORY_PRIOR_MEAN) / (count + design.HISTORY_ALPHA)
            if year in design.EXCLUDED_RELEASE_YEARS:
                continue
            for position in positions:
                if not np.isfinite(labels[position]):
                    continue
                for entity in memberships[position]:
                    prior_games.setdefault(entity, set()).add(int(position))
        output[f"{prefix}_prior_count"] = counts
        output[f"{prefix}_prior_hit_rate"] = rates
    result = pd.DataFrame(output, index=frame.index)
    design.assert_primary_feature_columns(result.columns)
    return result


def history_score(history: pd.DataFrame, future: pd.DataFrame, column: str, alpha: float = design.HISTORY_ALPHA) -> pd.Series:
    """Compatibility helper; score only the supplied strictly earlier history."""
    if alpha != design.HISTORY_ALPHA:
        raise ValueError("History alpha is frozen in config.py")
    unknown_future = future.copy()
    unknown_future[design.TARGET_COLUMN] = pd.NA
    combined = pd.concat([history, unknown_future], ignore_index=True)
    features = history_features(combined)
    prefix = {"developer": "dev", "publisher": "pub"}[column]
    return pd.Series(features[f"{prefix}_prior_hit_rate"].iloc[len(history):].to_numpy(), index=future.index)


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

    analytical = prepare_analytical(main)
    dates = analytical["release_date_utc"]
    owners_parts = main["owners"].astype(str).str.extract(r"^\s*([0-9,]+)\s*-\s*([0-9,]+)\s*$")
    owner_lower = pd.to_numeric(owners_parts[0].str.replace(",", ""), errors="coerce")
    owner_upper = pd.to_numeric(owners_parts[1].str.replace(",", ""), errors="coerce")
    owner_midpoint = (owner_lower + owner_upper) / 2
    reviews = main["positive_ratings"] + main["negative_ratings"]

    analytical["owner_midpoint"] = owner_midpoint
    owner_q90 = analytical.groupby("release_year")["owner_midpoint"].transform(
        lambda values: values.quantile(design.TARGET_QUANTILE, interpolation=design.TARGET_INTERPOLATION)
    )
    analytical["hit_owner_inclusive"] = analytical["owner_midpoint"].ge(owner_q90)
    through_2018 = analytical[analytical["split"].isin(("train", "validation", "test"))].copy()
    splits: dict[str, Any] = {}
    for name, mask in {
        f"train_through_{design.TRAIN_MAX_YEAR}": through_2018["split"].eq("train"),
        f"validation_{design.VALIDATION_YEAR}": through_2018["split"].eq("validation"),
        f"test_{design.TEST_YEAR}": through_2018["split"].eq("test"),
    }.items():
        split = through_2018[mask]
        splits[name] = {
            "rows": len(split),
            "positives": int(split[design.TARGET_COLUMN].sum()),
            "positive_rate_review_top_decile": float(split["hit_reviews"].mean()),
            "positive_rate_owner_q90_inclusive": float(split["hit_owner_inclusive"].mean()),
        }

    rule_baseline: dict[str, Any] = {}
    encoded_history = history_features(through_2018)
    for evaluation_year in (design.VALIDATION_YEAR, design.TEST_YEAR):
        history = through_2018[through_2018["release_year"].lt(evaluation_year)]
        future = through_2018[through_2018["release_year"].eq(evaluation_year)]
        if future.empty:
            continue
        developer_score = encoded_history.loc[future.index, "dev_prior_hit_rate"]
        publisher_score = encoded_history.loc[future.index, "pub_prior_hit_rate"]
        score = (
            design.RULE_BASELINE_ENTITY_WEIGHTS[0] * developer_score
            + design.RULE_BASELINE_ENTITY_WEIGHTS[1] * publisher_score
        )
        rule_baseline[str(evaluation_year)] = {
            "rows": len(future),
            "positive_rate": float(future["hit_reviews"].mean()),
            "history_rows": len(history),
            "history_max_release_year": int(history["release_year"].max()) if len(history) else None,
            "roc_auc": rank_auc(future["hit_reviews"], score),
            "average_precision": grouped_average_precision(future["hit_reviews"], score),
            "top_10_percent": tie_aware_top_fraction(future["hit_reviews"], score, design.EVALUATION_TOP_FRACTION),
            "unseen_developer_rate": float(encoded_history.loc[future.index, "dev_prior_count"].eq(0).mean()),
            "unseen_publisher_rate": float(encoded_history.loc[future.index, "pub_prior_count"].eq(0).mean()),
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
                "analytical_acceptance": "CONDITIONAL_GO" if all(structural_checks.values()) else "FAIL",
                "reason": (
                    "Use release-year top-decile total ratings as the primary popularity label, "
                    "exclude 2019, enforce chronological validation, and exclude post-release outcomes/tags."
                ),
            },
            "design": design.design_contract(),
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
                "invalid_release_date_count": int(dates.isna().sum()),
                "invalid_release_dates": main.loc[dates.isna(), ["appid", "release_date"]].to_dict("records"),
                "excluded_release_year_rows": int(analytical["split"].eq("excluded").sum()),
                "unknown_split_rows": int(analytical["split"].eq("unknown").sum()),
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
            "history_encoding": design.design_contract()["history"],
            "information_boundary": (
                "Retrospective 2019 snapshot: prior-release-year membership is enforced, "
                "but historical launch-time outcomes and attributes are not observed. "
                "Rolling 2018 rules include 2017 history; compare models using the same fit window."
            ),
            "feature_policy": design.design_contract()["feature_policy"],
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

    if args.output and args.output.exists():
        parser.error("--output already exists; choose a new run path to avoid overwriting results")

    result = audit(args.data_dir)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(rendered + "\n")


if __name__ == "__main__":
    main()
