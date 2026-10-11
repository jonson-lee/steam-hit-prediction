"""Versioned Steam design and adopted data policies.

Changing a design value requires a version bump and a decision-log entry.
Raw-data hashes and file schemas remain dataset-integrity checks, not design knobs.
v1.2 adds B05 data policies to the unchanged v1.1 business design. The policy
snapshot does not implement a parser or certify any existing data artifact.
"""

DESIGN_VERSION = "v1.2"
DESIGN_FROZEN_DATE = "2026-10-11"
BASE_DESIGN_VERSION = "v1.1"
BASE_DESIGN_FROZEN_DATE = "2026-09-24"
PARSE_POLICY_VERSION = "steam-parse/v1"
HANDOFF_CONTRACT_VERSION = "steam-handoff/v1"
DATA_POLICY_IMPLEMENTATION_STATUS = "implemented_real_file_acceptance_pending"
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

# Adopted by the user's B05 policy confirmation, recorded as D-024/D-025.
# These values are the machine policy source for the future implementation.
# Existing classify/helpers are not made conforming by declaring this snapshot.
DATA_PARSE_POLICY = {
    "version": PARSE_POLICY_VERSION,
    "implementation_status": DATA_POLICY_IMPLEMENTATION_STATUS,
    "raw_input": {"mode": "literal_strings", "preserve_original": True},
    "appid": {
        "key_type": "string", "strip": True, "pattern": "[0-9]+",
        "leading_zeros": "preserve", "minimum": 0,
        "maximum": 9223372036854775807, "float_intermediate": False,
        "order": "ASCII_lexicographic", "raw_output": "raw_appid",
        "key_output": "appid", "duplicates_or_collisions": "block_no_dedup",
        "apply_to": "primary_and_each_auxiliary_independently",
    },
    "missing": {
        "order": "preserve_raw_then_strip_then_field_specific_token_match",
        "classes": ("MISSING_EMPTY", "MISSING_WHITESPACE", "MISSING_DECLARED"),
        "tokens": ENTITY_MISSING_TOKENS, "token_case_sensitive": False,
        "token_fields": ("english", "required_age", "developer", "publisher",
                         "platforms", "categories", "genres"),
        "excluded_token_fields": ("appid", "release_date"),
        "extend_with_na": False, "imputation": "none",
    },
    "english": {"literals": ("0", "1"), "storage": "nullable_Int8",
                "invalid": "block", "missing": "preserve"},
    "required_age": {
        "mode": "MODE_INT", "pattern": r"[+-]?\d+",
        "unicode_decimal_digits": True, "minimum": 0,
        "storage_maximum": 9223372036854775807, "storage": "nullable_Int64",
        "semantic_maximum": None, "float_intermediate": False,
        "invalid": "block", "missing": "preserve",
    },
    "sequences": {
        "fields": ("developer", "publisher", "platforms", "categories", "genres"),
        "delimiter": ENTITY_DELIMITER, "trim_tokens": True,
        "drop_empty_tokens": True, "deduplication": "original_spelling_first_seen",
        "entity_case_sensitive": True, "unknown_tokens": "preserve_and_log",
        "alternate_delimiters": "literal_characters",
        "source_missing_wire_value": None, "source_missing_slot": "S_MISSING",
        "nonmissing_empty_wire_value": (), "nonmissing_empty_slot": "S_EMPTY_LIST",
        "missing_derived_sequence": (), "empty_string_element_source_output": False,
        "capture_source_class_before_lossy_helper": True,
    },
    "platform_membership": {"method": "case_insensitive_exact_token",
                            "tokens": ("windows", "mac", "linux"),
                            "missing_value": False},
    "sequence_counts": {"method": "length_after_deduplication",
                        "missing_value": 0, "storage": "Int64"},
    "ratings": {"pattern": "[0-9]+", "minimum": 0,
                "maximum": 9223372036854775807, "storage": "Int64",
                "sum": "exact_integer_checked_before_addition",
                "invalid_in_base_population": "block_package_keep_population",
                "invalid_outside_base_population": "diagnostic_only",
                "indeterminate_comparison": "no_label_block_package"},
    "uncovered_years": {"method": "isolate", "development_label": None,
                        "retain_full_year_population_statistics": True},
    "invalid_features": "block_package_preserve_raw_diagnostics",
    "test_year_policy_selection": "forbidden_apply_confirmed_rules_only",
}

DATA_HANDOFF_POLICY = {
    "version": HANDOFF_CONTRACT_VERSION,
    "implementation_status": DATA_POLICY_IMPLEMENTATION_STATUS,
    "format": "CSV_with_JSON_in_cell", "encoding": "utf-8",
    "bom": False, "newline": "\n", "csv_quoting": "QUOTE_ALL",
    "scalar_missing_sentinel": r"\N", "sentinel_collision": "block_and_version",
    "boolean_literals": ("true", "false"),
    "read": "literal_strings_then_explicit_column_schema_conversion",
    "json": {"ensure_ascii": False, "allow_nan": False,
             "separators": (",", ":"), "reject_duplicate_keys": True},
    "states": ("S_MISSING", "S_EMPTY_LIST", "S_EMPTY_STRING_ELEMENT", "S_LIST"),
    "reserved_source_state": "S_EMPTY_STRING_ELEMENT",
    "source_class_storage": "x_entity_states.source_missing_classes",
    "raw_parse_storage": "keys_meta.raw_parse_values",
    "row_disposition_precedence": ("invalid_key", "invalid_date_nat",
        "excluded_2019", "uncovered_year", "invalid_label_input",
        "train", "validation", "test"),
    "preserve_all_failure_codes": True,
    "hash_direction": ("stable_files", "manifest", "validation_report", "HANDOFF_READY"),
    "consumer_verification": "external_record_never_rewrite_sealed_report",
    "history_window": HISTORY_YEAR_POLICY,
    "history_fixed_2016_variant": "not_adopted_not_a_gate",
    "raw_provenance": "OFF", "snapshot_sensitivity": "OFF", "mutable_pointer": "OFF",
}


def data_policy_contract():
    """Independent policy snapshot; no parsing, data writes, fitting or validation."""
    from copy import deepcopy
    return {"parse": deepcopy(DATA_PARSE_POLICY), "handoff": deepcopy(DATA_HANDOFF_POLICY)}


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
        "business_design_base": {
            "version": BASE_DESIGN_VERSION, "frozen_date": BASE_DESIGN_FROZEN_DATE,
        },
        "data_policy_versions": {
            "parse": PARSE_POLICY_VERSION, "handoff": HANDOFF_CONTRACT_VERSION,
            "implementation_status": DATA_POLICY_IMPLEMENTATION_STATUS,
        },
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
