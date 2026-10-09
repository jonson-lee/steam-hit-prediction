"""Versioned Steam design contract, frozen by D-001 through D-023.

Changing a design value requires a version bump and a decision-log entry.
Raw-data hashes and file schemas remain dataset-integrity checks, not design knobs.
"""

DESIGN_VERSION = "v1.1"
DESIGN_FROZEN_DATE = "2026-09-24"
RELEASE_DATE_UTC = True
RELEASE_DATE_ERRORS = "coerce"
RELEASE_DATE_FORMAT = "mixed"

TARGET_COLUMN = "hit_reviews"
TARGET_QUANTILE = 0.90
TARGET_INTERPOLATION = "linear"
TARGET_INCLUSIVE = True
MIN_YEAR_GAMES = None  # D-022: retain even the smallest pre-2007 cohorts.
EXCLUDED_RELEASE_YEARS = (2019,)
TRAIN_MAX_YEAR = 2016
VALIDATION_YEAR = 2017
TEST_YEAR = 2018

ENTITY_DELIMITER = ";"
ENTITY_MISSING_TOKENS = ("unknown", "nan", "none", "null", "<na>")
HISTORY_ALPHA = 10.0
HISTORY_PRIOR_MEAN = 0.10
HISTORY_YEAR_POLICY = "strictly_earlier_release_years"
HISTORY_AGGREGATION = "union_prior_games_deduplicated"
HISTORY_COUNT_TRANSFORM = "log1p"
RULE_BASELINE_ENTITY_WEIGHTS = (0.5, 0.5)  # developer / publisher prior rates.
HISTORY_FEATURE_COLUMNS = (
    "dev_prior_count", "dev_prior_hit_rate", "pub_prior_count", "pub_prior_hit_rate",
)

MONTH_CYCLE_PERIOD = 12
MONTH_CYCLE_ORIGIN = 1
DAY_OF_WEEK_CYCLE_PERIOD = 7
DAY_OF_WEEK_CYCLE_ORIGIN = 0  # Monday=0, matching pandas dt.dayofweek.
CALENDAR_FEATURE_COLUMNS = (
    "release_month", "release_quarter", "release_day_of_week",
    "release_month_sin", "release_month_cos",
    "release_day_of_week_sin", "release_day_of_week_cos",
)

PRIMARY_RAW_COLUMNS = (
    "release_date", "english", "developer", "publisher", "platforms",
    "required_age", "categories", "genres",
)
PRIMARY_FEATURE_COLUMNS = (
    "english", "developer", "publisher", "platforms", "required_age", "categories", "genres",
    "has_windows", "has_mac", "has_linux", "platform_count", "category_count", "genre_count",
) + CALENDAR_FEATURE_COLUMNS + HISTORY_FEATURE_COLUMNS
METADATA_COLUMNS = ("appid", "name", "release_date", "release_date_utc", "release_year", "split")
SNAPSHOT_SENSITIVITY_COLUMNS = (
    "price", "achievements", "is_free", "is_free_true", "price_zero_unknown",
    "detailed_description", "about_the_game", "short_description",
    "pc_requirements", "mac_requirements", "linux_requirements", "minimum", "recommended",
    "header_image", "screenshots", "background", "movies",
    "website", "support_url", "support_email",
)
FORBIDDEN_PREDICTOR_COLUMNS = (
    "positive_ratings", "negative_ratings", "total_ratings", "total_votes",
    "positive_ratio", "positive_rate", "pos_rate", "owners", "owners_lo", "owners_hi",
    "owners_mid", "owner_midpoint", "log_owners_mid", "average_playtime", "median_playtime",
    "steamspy_tags", "tag_count", "tag_votes", "hit", "hit_reviews", "hit_quality",
    "hit_B", "hit_B_rank", "hit_owner_inclusive", "hit_att", "hit_A",
)
FORBIDDEN_SOURCES = ("steamspy_tag_data.csv",)
EVALUATION_TOP_FRACTION = 0.10


def assert_primary_feature_columns(columns):
    """Fail closed: only explicitly allowed primary inputs may enter X.

Apply before learned one-/multi-hot expansion. Derived features require an
explicit whitelist entry; merely renaming a blacklisted outcome does not grant
permission. IDs and cohort/target columns belong in separate aligned tables.
    """
    disallowed = sorted(set(columns) - set(PRIMARY_FEATURE_COLUMNS))
    if disallowed:
        raise ValueError(f"Not permitted in primary X: {disallowed}")
    return True


def design_contract():
    """JSON-ready record of the exact, centrally configured design semantics."""
    return {
        "version": DESIGN_VERSION,
        "frozen_date": DESIGN_FROZEN_DATE,
        "release_date": {
            "utc": RELEASE_DATE_UTC, "errors": RELEASE_DATE_ERRORS, "format": RELEASE_DATE_FORMAT,
        },
        "target": {
            "column": TARGET_COLUMN, "quantile": TARGET_QUANTILE,
            "interpolation": TARGET_INTERPOLATION, "inclusive": TARGET_INCLUSIVE,
            "minimum_cohort_size": MIN_YEAR_GAMES, "excluded_release_years": EXCLUDED_RELEASE_YEARS,
        },
        "split": {
            "train_max_year": TRAIN_MAX_YEAR, "validation_year": VALIDATION_YEAR, "test_year": TEST_YEAR,
        },
        "history": {
            "delimiter": ENTITY_DELIMITER, "year_policy": HISTORY_YEAR_POLICY,
            "aggregation": HISTORY_AGGREGATION, "count_transform": HISTORY_COUNT_TRANSFORM,
            "alpha": HISTORY_ALPHA, "prior_mean": HISTORY_PRIOR_MEAN,
            "missing_tokens": ENTITY_MISSING_TOKENS,
            "rule_baseline_entity_weights": RULE_BASELINE_ENTITY_WEIGHTS,
            "features": HISTORY_FEATURE_COLUMNS,
            "rate_formula": "(union_hits + alpha * prior_mean) / (union_count + alpha)",
        },
        "calendar": {
            "features": CALENDAR_FEATURE_COLUMNS,
            "month_period": MONTH_CYCLE_PERIOD, "month_origin": MONTH_CYCLE_ORIGIN,
            "day_of_week_period": DAY_OF_WEEK_CYCLE_PERIOD,
            "day_of_week_origin": DAY_OF_WEEK_CYCLE_ORIGIN,
        },
        "feature_policy": {
            "primary_raw_columns": PRIMARY_RAW_COLUMNS, "primary_features": PRIMARY_FEATURE_COLUMNS,
            "metadata_only": METADATA_COLUMNS,
            "sensitivity_only_snapshot_features": SNAPSHOT_SENSITIVITY_COLUMNS,
            "forbidden_predictors": FORBIDDEN_PREDICTOR_COLUMNS, "forbidden_sources": FORBIDDEN_SOURCES,
            "guard": "explicit_primary_whitelist_before_learned_expansion",
        },
        "top_fraction": EVALUATION_TOP_FRACTION,
    }
