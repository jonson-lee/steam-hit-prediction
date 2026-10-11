#!/usr/bin/env python3
"""Stage-0 read-only precheck for the primary Steam table (H04 draft v3).

Runs read-only and reports on stdout:
  * resolves config.py as the single machine-readable design source;
  * inventories dependencies by spec lookup and distribution metadata;
  * parses only appid plus config.PRIMARY_RAW_COLUMNS from one explicit CSV;
  * audits release dates and label-free field formats on the audit window
    (valid release_date AND release_year <= config.VALIDATION_YEAR).

Never:
  * reads label or outcome values (usecols is restricted, label builder is
    never called, positive counts / two-class conditions are not checked);
  * computes AP, ROC-AUC, Top-10% or rule-baseline scores;
  * builds vocabularies, one-/multi-hot matrices, X/y, history target
    encodings, imputers or scalers; imports or instantiates any estimator;
  * installs anything, switches tree family, or writes/overwrites any file.

A passing precheck is NOT a pipeline GO, NOT a freeze, NOT authorisation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import math
import re
import sys
import time
import traceback
from pathlib import Path

EXIT_CODE_MEANINGS = {
    0: "COMPLETED_CLEAN - no data blocker and no open precheck decision; "
       "still not a pipeline GO.",
    1: "BLOCKED_INVOCATION - CLI, config-resolution or input-encoding failure; "
       "the audit did not run.",
    2: "BLOCKED_ENVIRONMENT_CAPABILITY - numpy/pandas unusable, or a required "
       "pandas behaviour (mixed date parsing) raised.",
    3: "BLOCKED_DATA - fail-closed data finding: required column absent, "
       "appid violation, empty frame, all dates NaT, empty window queue, or "
       "illegal/unparseable values inside the audit window.",
    4: "COMPLETED_WITH_PENDING_ITEMS - no data blocker, but model-run "
       "dependencies are missing and/or field semantics need human decisions.",
    5: "INTERNAL_ERROR - unexpected failure; fail closed, no PASS reading.",
}

APPID_COLUMN = "appid"
DATE_COLUMN = "release_date"
CONFIG_NAMES = (
    "DESIGN_VERSION", "DESIGN_FROZEN_DATE", "RELEASE_DATE_UTC",
    "RELEASE_DATE_ERRORS", "RELEASE_DATE_FORMAT", "TARGET_COLUMN",
    "EXCLUDED_RELEASE_YEARS", "TRAIN_MAX_YEAR", "VALIDATION_YEAR", "TEST_YEAR",
    "ENTITY_DELIMITER", "ENTITY_MISSING_TOKENS", "HISTORY_ALPHA",
    "HISTORY_PRIOR_MEAN", "HISTORY_YEAR_POLICY", "MONTH_CYCLE_PERIOD",
    "DAY_OF_WEEK_CYCLE_PERIOD", "PRIMARY_RAW_COLUMNS", "PRIMARY_FEATURE_COLUMNS",
)
# Name-presence guard only. The values of these columns are never read.
OUTCOME_GUARD_NAMES = (
    "positive_ratings", "negative_ratings", "total_ratings", "is_positive",
    "owners", "estimate_owners", "estimate_age_group", "steamspy_tags",
    "tags", "tag_count", "price", "achievements", "number_of_assets",
    "playtime_forever", "playtime_windows_forever", "playtime_mac_forever",
    "playtime_linux_forever",
)
CANDIDATE_DELIMITERS = (",", ";", "|")
FINITE_DECIMAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
INTEGER_LITERAL = re.compile(r"^[+-]?\d+$")
NONFINITE_LITERAL = re.compile(r"^[+-]?(inf|infinity|nan)$", re.IGNORECASE)
APPID_DIGITS = re.compile(r"^\d+$")
APPID_LEADING_ZERO = re.compile(r"^0\d+$")

_CORE_IMPORT_ERROR = None
try:
    import numpy as np
    import pandas as pd
except Exception as exc:  # exit 2; never repaired at runtime
    np = None
    pd = None
    _CORE_IMPORT_ERROR = type(exc).__name__ + ": " + str(exc)


class Blocked(Exception):
    """Fail-closed stop. code is 1, 2 or 3; finding is {kind: detail}."""

    def __init__(self, code, kind, detail):
        super().__init__(detail)
        self.code = code
        self.finding = {kind: detail}


def to_native(value):
    if isinstance(value, dict):
        return {str(k): to_native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_native(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if value is None or isinstance(value, str):
        return value
    if np is not None and isinstance(value, np.integer):
        return int(value)
    if np is not None and isinstance(value, np.floating):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if pd is not None and isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def missing_token_set(config):
    return frozenset(str(token).lower()
                     for token in config.ENTITY_MISSING_TOKENS)


def classify(raw, missing_tokens):
    text = "" if raw is None else str(raw)
    if text == "":
        return "empty_cell"
    if text.strip() == "":
        return "whitespace_only_cell"
    if text.lower() in missing_tokens:
        return "declared_missing_token"
    stripped = text.strip()
    if INTEGER_LITERAL.match(stripped):
        return "finite_integer"
    if FINITE_DECIMAL.match(stripped):
        return "finite_decimal"
    if NONFINITE_LITERAL.match(stripped):
        return "non_finite_literal"
    return "other_unparseable"


def split_entities(raw, delimiter, missing_tokens):
    """Local reproduction of the confirmed developer/publisher semantics.

    Delimiter and missing tokens come from config, so no second frozen
    constant set is introduced. Reconciling this helper with the production
    one is listed as an open item; neither has been executed here.
    """
    if raw is None or (pd is not None and pd.isna(raw)):
        return ()
    kept = [item.strip() for item in str(raw).split(delimiter)]
    kept = [item for item in kept if item]
    return tuple(dict.fromkeys(
        item for item in kept if item.lower() not in missing_tokens))


# --------------------------------------------------------------------------
# A. config and environment
# --------------------------------------------------------------------------
def resolve_config():
    root = Path(__file__).resolve().parents[1]
    path = root / "config.py"
    if not path.is_file():
        raise Blocked(1, "CONFIG_NOT_FOUND",
                      "config.py not found at the project root inferred from "
                      "scripts/: " + str(path))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    module = importlib.import_module("config")
    absent = [name for name in CONFIG_NAMES if not hasattr(module, name)]
    if absent:
        raise Blocked(1, "CONFIG_NAMES_MISSING",
                      "config.py does not define: " + ", ".join(absent))
    return module


def snapshot_config(config):
    markers = tuple(name[len("has_"):] for name in config.PRIMARY_FEATURE_COLUMNS
                    if isinstance(name, str) and name.startswith("has_"))
    return {
        "path": str(config.__file__),
        "sha256": sha256_file(Path(config.__file__)),
        "design_version": config.DESIGN_VERSION,
        "design_frozen_date": config.DESIGN_FROZEN_DATE,
        "release_date_policy": {
            "utc": config.RELEASE_DATE_UTC,
            "errors": config.RELEASE_DATE_ERRORS,
            "format": config.RELEASE_DATE_FORMAT,
        },
        "target_column": config.TARGET_COLUMN,
        "target_values_read": False,
        "year_windows": {
            "train_max_year": config.TRAIN_MAX_YEAR,
            "validation_year": config.VALIDATION_YEAR,
            "test_year": config.TEST_YEAR,
            "excluded_release_years": list(config.EXCLUDED_RELEASE_YEARS),
        },
        "entity_delimiter": config.ENTITY_DELIMITER,
        "entity_missing_tokens": list(config.ENTITY_MISSING_TOKENS),
        "history": {
            "alpha": config.HISTORY_ALPHA,
            "prior_mean": config.HISTORY_PRIOR_MEAN,
            "year_policy": config.HISTORY_YEAR_POLICY,
        },
        "calendar_cycle_constants": {
            "month_period": config.MONTH_CYCLE_PERIOD,
            "day_of_week_period": config.DAY_OF_WEEK_CYCLE_PERIOD,
        },
        "primary_raw_columns": list(config.PRIMARY_RAW_COLUMNS),
        "primary_feature_column_count": len(config.PRIMARY_FEATURE_COLUMNS),
        "derived_membership_markers": list(markers),
    }


def probe(module_name, distribution_name):
    importable = importlib.util.find_spec(module_name) is not None
    version, status = None, "NOT_INSTALLED"
    if importable:
        try:
            version = importlib.metadata.version(distribution_name)
            status = "VERSION_IDENTIFIED_API_COMPAT_UNVERIFIED"
        except importlib.metadata.PackageNotFoundError:
            status = "IMPORTABLE_BUT_NO_DIST_METADATA"
    return {"distribution": distribution_name, "importable": importable,
            "version": version, "version_status": status}


def environment_inventory(config, tree_branch):
    blockers, pending = {}, []
    core = {
        "numpy": {"importable": np is not None,
                  "version": None if np is None else np.__version__},
        "pandas": {"importable": pd is not None,
                   "version": None if pd is None else pd.__version__},
        "core_import_error": _CORE_IMPORT_ERROR,
    }
    if not core["numpy"]["importable"]:
        blockers["NUMPY_UNUSABLE"] = "numpy cannot be imported; audit aborted."
    if not core["pandas"]["importable"]:
        blockers["PANDAS_UNUSABLE"] = "pandas cannot be imported; audit aborted."
    modeling = {
        "scikit_learn": probe("sklearn", "scikit-learn"),
        "scipy": probe("scipy", "scipy"),
        "xgboost": probe("xgboost", "xgboost"),
    }
    needed = ["scikit_learn", "scipy"]
    if tree_branch == "xgb":
        needed = needed + ["xgboost"]
    for name in needed:
        if not modeling[name]["importable"]:
            pending.append(
                name + " is not importable, so the LR branch"
                + (" and the requested XGB branch" if name == "xgboost" else "")
                + " cannot fit. Reported only: nothing installed, tree family "
                "not switched, no attempt made to run the other family.")
    if core["pandas"]["importable"]:
        pending.append(
            "pd.to_datetime(format=" + repr(config.RELEASE_DATE_FORMAT)
            + ") support is probed by actually parsing below; a version "
            "number alone never proves API compatibility.")
    return {
        "python": {"version": sys.version.split()[0],
                   "implementation": sys.implementation.name},
        "core": core,
        "modeling": modeling,
        "branch": {
            "requested": tree_branch,
            "needed_by_requested_branch": needed,
            "note": "Dependency branch selector for this precheck only. It "
                    "does not declare the final tree family as adopted and "
                    "has no silent fallback.",
        },
        "blockers": blockers,
        "pending": pending,
    }


# --------------------------------------------------------------------------
# B/C. restricted read and structural checks
# --------------------------------------------------------------------------
def read_header(path, encoding):
    try:
        with path.open("r", encoding=encoding, newline="") as handle:
            row = next(csv.reader(handle), None)
    except UnicodeDecodeError as exc:
        raise Blocked(1, "HEADER_ENCODING_FAILURE",
                      "Header is not decodable as " + encoding + " at byte "
                      "offset " + str(getattr(exc, "start", -1))
                      + "; declare the encoding, no auto-detection is done.") from exc
    except OSError as exc:
        raise Blocked(1, "HEADER_UNREADABLE", repr(exc)) from exc
    if not row:
        raise Blocked(3, "EMPTY_FILE", "CSV header row is empty.")
    names = [str(name).strip() for name in row]
    if len(names) != len(set(names)):
        raise Blocked(3, "DUPLICATE_HEADER_NAMES",
                      "Header contains duplicate column names.")
    return names


def read_frame(path, header, raw_columns, encoding):
    required = [APPID_COLUMN] + [name for name in raw_columns
                                 if name != APPID_COLUMN]
    absent = [name for name in required if name not in header]
    if absent:
        raise Blocked(3, "REQUIRED_COLUMNS_MISSING",
                      "Header lacks: " + ", ".join(absent))
    try:
        return pd.read_csv(
            path, sep=",", dtype=str, usecols=required, encoding=encoding,
            engine="c", quotechar='"', doublequote=True,
            skipinitialspace=False, keep_default_na=False, na_filter=False,
            low_memory=False,
        ), required
    except UnicodeDecodeError as exc:
        raise Blocked(1, "BODY_ENCODING_FAILURE",
                      "Body is not decodable as " + encoding
                      + "; declare the encoding, no fallback is attempted.") from exc
    except ValueError as exc:
        raise Blocked(3, "CSV_STRUCTURE_INVALID", repr(exc)) from exc
    except OSError as exc:
        raise Blocked(1, "CSV_UNREADABLE", repr(exc)) from exc


def parse_dates(frame, config):
    try:
        return pd.to_datetime(
            frame[DATE_COLUMN], errors=config.RELEASE_DATE_ERRORS,
            utc=config.RELEASE_DATE_UTC, format=config.RELEASE_DATE_FORMAT)
    except (ValueError, TypeError) as exc:
        raise Blocked(2, "DATE_PARSE_CAPABILITY",
                      "pd.to_datetime rejected the config date policy "
                      "(format=" + repr(config.RELEASE_DATE_FORMAT) + "): "
                      + repr(exc) + ". Environment/API capability gap, not a "
                      "data fault; the audit window cannot be defined.") from exc


def appid_above_int64_max(digits):
    # Called only for digit strings; compare magnitudes without float rounding.
    normalised = "".join(str(int(char)) for char in digits).lstrip("0") or "0"
    bound = str(np.iinfo(np.int64).max)
    return (len(normalised) > len(bound)
            or (len(normalised) == len(bound) and normalised > bound))


def audit_appid(frame):
    series = frame[APPID_COLUMN]
    stripped = series.str.strip()
    non_empty = stripped.ne("")
    report = {
        "rows_total": int(len(frame)),
        "empty_cell": int(series.eq("").sum()),
        "whitespace_only_cell": int(series.ne(stripped).mul(
            stripped.eq("")).sum()),
        "non_digit_string": int(non_empty.mul(
            ~stripped.str.match(APPID_DIGITS, na=False)).sum()),
        "leading_zero_rows": int(stripped.str.match(APPID_LEADING_ZERO,
                                                    na=False).sum()),
        "duplicate_raw_value_rows": int(series.ne("").mul(
            series.duplicated(keep=False)).sum()),
        "duplicate_after_strip_rows": int(
            stripped[non_empty].duplicated(keep=False).sum()),
        "duplicate_count_policy": (
            "The two duplicate counts use different bases and overlap, so they "
            "must never be added together. raw basis: over raw values, "
            "excluding only the raw empty string, so duplicated pure-whitespace "
            "cells are still counted. strip basis: over values that are "
            "non-empty after stripping, so cells that strip to empty are "
            "excluded entirely. Neither is a subset of the other: two pure-"
            "whitespace cells appear only in the raw count, while \"1\" and "
            "\" 1 \" collide only in the strip count. APPID_DUPLICATE is "
            "driven by the strip basis, as in R3."),
        "distinct_after_strip": int(stripped[non_empty].nunique()),
        "rows_above_int64_max": int(0),
        "uniqueness_rule": "appid must be present, digit-only and unique "
                           "across the frame",
    }
    digits = stripped[non_empty & stripped.str.match(APPID_DIGITS, na=False)]
    report["rows_above_int64_max"] = sum(
        appid_above_int64_max(value) for value in digits)
    report["appid_policy_status"] = (
        "Strip-then-compare is an audit convention. Leading-zero "
        "normalisation and the accepted integer domain remain pending; "
        "their counts are evidence only.")
    blockers = {}
    if report["empty_cell"] + report["whitespace_only_cell"]:
        blockers["APPID_MISSING"] = (
            str(report["empty_cell"] + report["whitespace_only_cell"])
            + " row(s) have an empty or whitespace-only appid.")
    if report["non_digit_string"]:
        blockers["APPID_ILLEGAL"] = (
            str(report["non_digit_string"]) + " row(s) have a non-digit appid.")
    if report["duplicate_after_strip_rows"]:
        blockers["APPID_DUPLICATE"] = (
            str(report["duplicate_after_strip_rows"])
            + " row(s) share an appid after stripping whitespace.")
    return report, blockers


def audit_dates(frame, parsed, config):
    valid = parsed.notna()
    years = parsed.dt.year[valid].astype("int64")
    by_year = {int(year): int(count)
               for year, count in years.value_counts().sort_index().items()}
    excluded = [int(year) for year in config.EXCLUDED_RELEASE_YEARS]
    train_max = int(config.TRAIN_MAX_YEAR)
    validation = int(config.VALIDATION_YEAR)
    test = int(config.TEST_YEAR)
    report = {
        "rows_total": int(len(frame)),
        "parsed_non_null": int(valid.sum()),
        "nat_rows": int(parsed.isna().sum()),
        "empty_date_cell": int(frame[DATE_COLUMN].str.strip().eq("").sum()),
        "years_present": by_year,
        "min_year": min(by_year) if by_year else None,
        "max_year": max(by_year) if by_year else None,
        "excluded_year_rows": int(sum(by_year.get(year, 0) for year in excluded)),
        "fit_window_rows_le_train_max_year": int(sum(
            count for year, count in by_year.items() if year <= train_max)),
        "selection_year_rows": int(by_year.get(validation, 0)),
        "test_year_rows": int(by_year.get(test, 0)),
        "rows_after_test_year": int(sum(
            count for year, count in by_year.items() if year > test)),
        "rows_in_uncovered_years": int(sum(
            count for year, count in by_year.items()
            if year > train_max and year not in (validation, test)
            and year not in excluded)),
        "audit_scope_definition": (
            "valid release_date AND release_year <= config.VALIDATION_YEAR, so "
            "config.TEST_YEAR rows never enter the format audit and cannot "
            "drive preprocessing choices"),
        "upstream_frame_policy": "no row dropped, no original field overwritten",
        "calendar_note": "Calendar feature generation is not re-derived or "
                         "re-verified here; its existing behaviour is GPT-"
                         "verified evidence, not a result of this run.",
    }
    blockers, pending = {}, []
    if report["rows_total"] and report["parsed_non_null"] == 0:
        blockers["ALL_DATES_INVALID"] = (
            "Every release_date is NaT under the config date policy.")
    if report["fit_window_rows_le_train_max_year"] == 0:
        blockers["NO_FIT_WINDOW_ROWS"] = (
            "No valid row with release_year <= config.TRAIN_MAX_YEAR, so no "
            "fit window queue exists.")
    if report["selection_year_rows"] == 0:
        blockers["NO_SELECTION_YEAR_ROWS"] = (
            "No valid row in config.VALIDATION_YEAR, so selection scoring has "
            "no queue.")
    if report["test_year_rows"] == 0:
        pending.append("No valid row in config.TEST_YEAR: the final scoring "
                       "queue would be empty.")
    if report["rows_in_uncovered_years"]:
        pending.append(str(report["rows_in_uncovered_years"]) + " valid row(s) "
                       "sit in years covered by neither the fit window, the "
                       "selection year, the test year nor the excluded years; "
                       "their disposition must be stated before freezing.")
    return report, blockers, pending


# --------------------------------------------------------------------------
# D. field format audit (audit window only)
# --------------------------------------------------------------------------
def audit_english(series, config):
    missing_tokens = missing_token_set(config)
    counts = {"empty_cell": 0, "whitespace_only_cell": 0,
              "declared_missing_token": 0, "legal_zero": 0, "legal_one": 0,
              "illegal_non_empty_value": 0}
    for raw in series:
        kind = classify(raw, missing_tokens)
        if kind in ("empty_cell", "whitespace_only_cell",
                    "declared_missing_token"):
            counts[kind] += 1
            continue
        text = str(raw).strip()
        if text == "0":
            counts["legal_zero"] += 1
        elif text == "1":
            counts["legal_one"] += 1
        else:
            counts["illegal_non_empty_value"] += 1
    counts["rows_in_scope"] = int(len(series))
    counts["accepted_literal_domain"] = ["0", "1"]
    counts["accepted_rule"] = (
        "strip, then accept exactly 0 or 1. Missing means an empty cell or a "
        "config.ENTITY_MISSING_TOKENS value compared case-insensitively. Any "
        "other non-empty value is a parse failure and is never folded into "
        "missing. Proposed rule, not a frozen one.")
    counts["missing_value_policy_proposal"] = (
        "impute with the fit-window mode; ties resolve to 0; an all-missing "
        "column resolves to 0. Declared as a proposal only.")
    return counts


def audit_numeric(series, name, config):
    missing_tokens = missing_token_set(config)
    counts = {key: 0 for key in (
        "empty_cell", "whitespace_only_cell", "declared_missing_token",
        "finite_integer", "finite_decimal", "non_finite_literal",
        "out_of_range_after_conversion", "other_unparseable")}
    accepted = []
    for raw in series:
        kind = classify(raw, missing_tokens)
        if kind in ("finite_integer", "finite_decimal"):
            try:
                value = float(str(raw).strip())
            except (ValueError, OverflowError):
                kind = "out_of_range_after_conversion"
            else:
                if math.isfinite(value):
                    accepted.append(value)
                else:
                    kind = "out_of_range_after_conversion"
        counts[kind] += 1
    report = {
        "rows_in_scope": int(len(series)),
        "class_counts": counts,
        "accepted_value_min": min(accepted) if accepted else None,
        "accepted_value_max": max(accepted) if accepted else None,
        "accepted_negative_rows": int(sum(1 for value in accepted if value < 0)),
        "accepted_zero_rows": int(sum(1 for value in accepted if value == 0)),
        "accepted_positive_rows": int(sum(1 for value in accepted if value > 0)),
        "accepted_rule": (
            "strip, then accept a finite integer or decimal literal, optionally "
            "signed and optionally with an exponent. Non-empty values that "
            "cannot convert, and +/-Inf, are parse failures to be counted and "
            "failed closed, never silently coerced into missing. Proposed rule "
            "for " + name + ", not a frozen one."),
        "literal_nan_classified_as": (
            "declared_missing_token" if "nan" in missing_tokens
            else "non_finite_literal"),
        "missing_value_policy_proposal": (
            "real missing goes to the fit-window median imputation; an "
            "all-missing column is filled with 0; only missing cells are "
            "replaced. No indicator column, no silent drop or clipping."),
    }
    return report


def audit_entity_field(frame, column, mask, config):
    missing_tokens = missing_token_set(config)
    delimiter = str(config.ENTITY_DELIMITER)
    others = tuple(item for item in CANDIDATE_DELIMITERS if item != delimiter)
    report = {key: 0 for key in (
        "rows_in_scope", "empty_cell", "whitespace_only_cell",
        "declared_missing_token", "populated_rows",
        "rows_resolving_to_zero_entities", "rows_resolving_to_one_entity",
        "rows_resolving_to_multiple_entities", "entity_total_after_dedup",
        "rows_with_inline_duplicate_entities",
        "rows_with_inline_missing_token",
        "rows_with_whitespace_padded_entity_tokens",
        "rows_containing_config_delimiter",
        "rows_containing_other_delimiter_placeholder")}
    report.pop("rows_containing_other_delimiter_placeholder")
    report["rows_in_scope"] = int(mask.sum())
    report["rows_containing_other_delimiter"] = {item: 0 for item in others}
    spellings = {}
    for raw in frame.loc[mask, column]:
        kind = classify(raw, missing_tokens)
        if kind in ("empty_cell", "whitespace_only_cell",
                    "declared_missing_token"):
            report[kind] += 1
            continue
        text = str(raw)
        report["populated_rows"] += 1
        if delimiter in text:
            report["rows_containing_config_delimiter"] += 1
        for other in others:
            if other in text:
                report["rows_containing_other_delimiter"][other] += 1
        parts = text.split(delimiter)
        # Row-level evidence: the cell carries the config delimiter and at
        # least one non-empty token that is a declared missing token after
        # strip + lower. Several such tokens still count once. Empty tokens
        # are never treated as declared missing, and cells already classified
        # as whole-cell missing above never reach this branch.
        if delimiter in text and any(
                item.strip().lower() in missing_tokens
                for item in parts if item.strip()):
            report["rows_with_inline_missing_token"] += 1
        kept = [item.strip() for item in parts
                if item.strip() and item.strip().lower() not in missing_tokens]
        unique = split_entities(raw, delimiter, missing_tokens)
        if len(unique) != len(kept):
            report["rows_with_inline_duplicate_entities"] += 1
        if any(item != item.strip() for item in parts if item.strip()):
            report["rows_with_whitespace_padded_entity_tokens"] += 1
        if not unique:
            report["rows_resolving_to_zero_entities"] += 1
        elif len(unique) == 1:
            report["rows_resolving_to_one_entity"] += 1
        else:
            report["rows_resolving_to_multiple_entities"] += 1
        report["entity_total_after_dedup"] += len(unique)
        for item in unique:
            spellings.setdefault(item.lower(), set()).add(item)
    variant_groups = [group for group in spellings.values() if len(group) > 1]
    variant_keys = set()
    for group in variant_groups:
        variant_keys.update(item.lower() for item in group)
    affected = 0
    for raw in frame.loc[mask, column]:
        if any(item.lower() in variant_keys
               for item in split_entities(raw, delimiter, missing_tokens)):
            affected += 1
    report["case_variant_lowercase_key_groups"] = len(variant_groups)
    report["case_variant_affected_rows"] = affected
    report["distinct_entity_spellings_in_scope"] = int(sum(
        len(group) for group in spellings.values()))
    report["distinct_lowercase_keys_in_scope"] = len(spellings)
    report["parse_rule_source"] = (
        "Local reproduction of the confirmed split/strip/empty-drop/case-"
        "insensitive-missing/inline-dedupe semantics, driven by config "
        "constants. Entity spelling itself stays case-sensitive. Reconciling "
        "this with the production helper is an open item.")
    return report


def audit_multivalue_field(frame, column, mask, config, markers):
    missing_tokens = missing_token_set(config)
    report = {
        "rows_in_scope": int(mask.sum()),
        "empty_cell": 0, "whitespace_only_cell": 0,
        "declared_missing_token": 0, "populated_rows": 0,
        "delimiter_row_counts": {}, "delimiter_occurrence_totals": {},
        "delimiter_breadth_rows": {"none": 0, "one": 0, "two_or_more": 0},
        "rows_with_comma_and_semicolon": 0,
        "rows_with_leading_or_trailing_space": 0,
        "rows_wrapped_in_brackets": 0,
        "marker_evidence_under_each_hypothesis": {},
        "semantics_status": "NOT_ADOPTED_FORMAT_EVIDENCE_ONLY",
    }
    series = frame.loc[mask, column]
    for delimiter in CANDIDATE_DELIMITERS:
        report["delimiter_row_counts"][delimiter] = int(
            series.str.contains(re.escape(delimiter), regex=True).sum())
        report["delimiter_occurrence_totals"][delimiter] = int(
            series.str.count(re.escape(delimiter)).astype("int64").sum())
    for raw in series:
        kind = classify(raw, missing_tokens)
        if kind in ("empty_cell", "whitespace_only_cell",
                    "declared_missing_token"):
            report[kind] += 1
            continue
        text = str(raw)
        report["populated_rows"] += 1
        hits = [item for item in CANDIDATE_DELIMITERS if item in text]
        if len(hits) >= 2:
            report["delimiter_breadth_rows"]["two_or_more"] += 1
        elif len(hits) == 1:
            report["delimiter_breadth_rows"]["one"] += 1
        else:
            report["delimiter_breadth_rows"]["none"] += 1
        if "," in text and ";" in text:
            report["rows_with_comma_and_semicolon"] += 1
        if text != text.strip():
            report["rows_with_leading_or_trailing_space"] += 1
        if text.startswith("[") and text.endswith("]"):
            report["rows_wrapped_in_brackets"] += 1
    for delimiter in CANDIDATE_DELIMITERS:
        per_marker = {}
        for marker in markers:
            lowered = marker.lower()
            exact_case = exact_ci = substring_ci = 0
            for raw in series:
                text = "" if raw is None else str(raw)
                if text.strip() == "":
                    continue
                parts = [item.strip() for item in text.split(delimiter)]
                if marker in parts:
                    exact_case += 1
                if lowered in [item.lower() for item in parts]:
                    exact_ci += 1
                if lowered in text.lower():
                    substring_ci += 1
            per_marker[marker] = {
                "token_exact_case_rows": exact_case,
                "token_case_insensitive_rows": exact_ci,
                "raw_substring_case_insensitive_rows": substring_ci,
            }
        report["marker_evidence_under_each_hypothesis"][delimiter] = per_marker
    report["note"] = (
        "Every candidate delimiter is evaluated as an unadopted hypothesis so a "
        "human can decide the split rule, casing and has_* membership. No "
        "delimiter, casing or membership rule is adopted here, and "
        "platform_count / category_count / genre_count are not computed in this "
        "run.")
    return report


# --------------------------------------------------------------------------
# E. coverage, pending items, verdict
# --------------------------------------------------------------------------
COVERED_CHECKS = [
    "config.py resolution, sha256 fingerprint and echoed design values",
    "dependency inventory via find_spec plus distribution metadata; no "
    "estimator imported or instantiated",
    "restricted read of appid + config.PRIMARY_RAW_COLUMNS only",
    "header schema and outcome/label column presence by name only",
    "appid missing / illegal / duplicate / above int64",
    "date parsing under the config policy: per-year counts, excluded-year, "
    "NaT, fit-window, selection-year and test-year counts",
    "english and required_age format classification inside the audit window",
    "developer/publisher evidence under the confirmed parse rules",
    "platforms/categories/genres delimiter, missing and membership format "
    "evidence under every unadopted hypothesis",
]
NOT_COVERED = [
    "label construction, positive counts and the two-class fit condition: "
    "this run never reads label or outcome values, so these are unverified",
    "AP, ROC-AUC, Top-10% and rule-baseline scores",
    "learned vocabularies, min_count filtering, one-/multi-hot expansion",
    "imputers, StandardScaler fits, zero-variance handling, the final CSR "
    "float64 matrix and its dtype conversion behaviour",
    "history target encoding, per-row strictly-earlier-window checks and "
    "source-window bookkeeping",
    "whitelist gate assert_primary_feature_columns before expansion, and "
    "source-mapping coverage after expansion",
    "any model import, fit, convergence, failure branch or LOCK_NONE state",
    "calendar feature generation and its boundary behaviour",
    "seed, dependency version, thread and cross-machine reproducibility",
    "training runtime and cost",
    "formal freeze record and execution authorisation",
]
PENDING_DECISIONS = [
    "appid leading-zero normalisation and accepted integer domain",
    "final tree family and dependency versions",
    "selected versions' API compatibility and effective default parameters",
    "platforms/categories/genres parsing and has_* membership semantics",
    "english/required_age true-missing and illegal-value handling",
    "formal matrix assembly, source mapping and dtype conversion",
    "label and positive-count / two-class verification (out of scope here)",
    "formal convergence, reproducibility, runtime and cost",
    "formal freeze record and subsequent execution authorisation",
]
SCOPE_GUARDS = {
    "outcome_or_label_values_read": False,
    "label_builder_called": False,
    "metrics_computed": False,
    "rule_baseline_scored": False,
    "vocab_or_imputer_or_scaler_built": False,
    "history_or_matrix_built": False,
    "model_imported_or_fitted": False,
    "anything_installed": False,
    "tree_family_switched_or_downgraded": False,
    "file_written": False,
    "test_year_rows_used_for_audit": False,
    "candidate_grid_extended": False,
    "rows_silently_dropped": False,
    "original_fields_overwritten": False,
}


CHECK_STAGES = (
    ("input_exists", "explicit input file exists"),
    ("config", "config resolution, fingerprint and design snapshot"),
    ("environment", "dependency inventory; compatibility remains unverified"),
    ("header", "CSV header is nonempty and has no duplicate names"),
    ("read", "restricted read of appid plus PRIMARY_RAW_COLUMNS"),
    ("header_names", "outcome-column presence checked by name only"),
    ("appid", "appid missingness, duplicates and range evidence"),
    ("dates", "date parsing and year-window counts"),
    ("scope", "valid-date audit mask through VALIDATION_YEAR"),
    ("english", "english format audit inside the audit window"),
    ("required_age", "required_age format and finiteness audit"),
    ("entities", "present developer/publisher fields audited"),
    ("multivalue", "present platforms/categories/genres fields audited"),
)


def mark(report, stage):
    report["completed_stages"].append(stage)


def finalize_coverage(report, code):
    completed = report["completed_stages"]
    findings = report.get("blocking_findings", {})
    reason = ", ".join(sorted(findings)) or report.get("verdict", "stage not reached")
    checks = report.setdefault("checks", {})
    checks.pop("covered", None)
    checks["planned_checks"] = [description for _, description in CHECK_STAGES]
    checks["checks_completed_this_run"] = [
        {"stage": stage, "description": description}
        for stage, description in CHECK_STAGES if stage in completed]
    checks["checks_not_run_this_run"] = [
        {"stage": stage, "description": description,
         "reason": reason + " / exit " + str(code)}
        for stage, description in CHECK_STAGES if stage not in completed]
    checks.setdefault("not_covered", NOT_COVERED)
    checks.setdefault("pending_human_decisions", PENDING_DECISIONS)
    checks.setdefault("scope_guards", SCOPE_GUARDS)


def choose_exit_code(blocking, pending):
    if blocking:
        return blocking.get("_code", 3)
    if pending:
        return 4
    return 0


def emit(report, code):
    finalize_coverage(report, code)
    report["exit_code"] = code
    report["exit_code_meaning"] = EXIT_CODE_MEANINGS[code]
    try:
        text = json.dumps(to_native(report), indent=2, sort_keys=True,
                          allow_nan=False)
    except (ValueError, TypeError) as exc:
        print("[stage0_precheck] JSON sanitisation failed: " + repr(exc),
              file=sys.stderr)
        code = 5
        text = json.dumps({"status": "INTERNAL_ERROR",
                           "verdict": "REPORT_NOT_SERIALISABLE",
                           "exit_code": 5,
                           "exit_code_meaning": EXIT_CODE_MEANINGS[5]},
                          indent=2, sort_keys=True)
    print(text)
    return code


def run(args, report):
    if not args.input_main.is_file():
        raise Blocked(1, "INPUT_NOT_FOUND",
                      str(args.input_main) + " is not a readable file.")
    mark(report, "input_exists")
    config = resolve_config()
    report["config"] = snapshot_config(config)
    mark(report, "config")
    environment = environment_inventory(config, args.tree)
    mark(report, "environment")
    report["environment"] = {
        "python": environment["python"], "core": environment["core"],
        "modeling": environment["modeling"], "branch": environment["branch"],
    }
    blocking = dict(environment["blockers"])
    pending = list(environment["pending"])
    if blocking:
        code = 2 if "PANDAS_UNUSABLE" in blocking or "NUMPY_UNUSABLE" in blocking else 1
        blocking["_code"] = code
        return blocking, pending, report

    header = read_header(args.input_main, args.encoding)
    mark(report, "header")
    frame, used = read_frame(args.input_main, header,
                             list(config.PRIMARY_RAW_COLUMNS), args.encoding)
    mark(report, "read")
    markers = tuple(name[len("has_"):] for name in config.PRIMARY_FEATURE_COLUMNS
                    if isinstance(name, str) and name.startswith("has_"))
    guard_names = OUTCOME_GUARD_NAMES + (config.TARGET_COLUMN,)
    report["input"] = {
        "header_column_count": len(header),
        "columns_used_for_values": used,
        "unused_header_columns": [name for name in header if name not in used],
        "outcome_guard_columns_present": [name for name in guard_names
                                          if name in header],
        "outcome_guard_note": "Name presence only; those columns were never "
                              "parsed into the frame or used.",
        "rows_read": int(len(frame)),
        "read_policy": {
            "dtype": "str", "keep_default_na": False, "na_filter": False,
            "skipinitialspace": False, "sep": ",", "quotechar": '"',
            "doublequote": True, "encoding": args.encoding,
            "rationale": "Raw strings are preserved so empty cells, declared "
                         "missing tokens and parse failures stay separable "
                         "instead of being masked by pandas default NA "
                         "conversion. This is a precheck draft strategy; the "
                         "formal feature pipeline is not claimed to share it.",
        },
    }
    mark(report, "header_names")
    if len(frame) == 0:
        blocking["_code"] = 3
        blocking["NO_ROWS"] = "CSV has a header but no data rows."
        return blocking, pending, report

    appid_report, appid_blockers = audit_appid(frame)
    mark(report, "appid")
    report["appid_audit"] = appid_report
    blocking.update(appid_blockers)

    parsed = parse_dates(frame, config)
    date_report, date_blockers, date_pending = audit_dates(frame, parsed, config)
    mark(report, "dates")
    report["date_audit"] = date_report
    blocking.update(date_blockers)
    pending.extend(date_pending)

    mask = parsed.notna() & (parsed.dt.year <= int(config.VALIDATION_YEAR))
    report["field_audit_scope"] = {
        "definition": "valid release_date AND release_year <= "
                      "config.VALIDATION_YEAR",
        "rows_in_scope": int(mask.sum()),
        "rows_total": int(len(frame)),
        "test_year_rows_excluded": int((parsed.notna() & (
            parsed.dt.year == int(config.TEST_YEAR))).sum()),
        "used_to_select_preprocessing": False,
    }
    mark(report, "scope")
    if int(mask.sum()) == 0:
        blocking["_code"] = 3
        blocking["EMPTY_AUDIT_SCOPE"] = (
            "No valid-date row with release_year <= config.VALIDATION_YEAR, so "
            "the field-format audit has no queue.")
        report["field_audit"] = None
    else:
        scoped = frame.loc[mask]
        fields = {}
        if "english" in scoped.columns:
            fields["english"] = audit_english(scoped["english"], config)
            mark(report, "english")
            if fields["english"]["illegal_non_empty_value"]:
                blocking.setdefault("_code", 3)
                blocking["ENGLISH_ILLEGAL_VALUE"] = (
                    str(fields["english"]["illegal_non_empty_value"])
                    + " english row(s) in the audit window are non-empty but "
                    "outside {0,1}; fail closed unless a parsing policy is "
                    "declared before stage 0.")
        if "required_age" in scoped.columns:
            numeric = audit_numeric(scoped["required_age"], "required_age", config)
            fields["required_age"] = numeric
            mark(report, "required_age")
            bad = (numeric["class_counts"]["non_finite_literal"]
                   + numeric["class_counts"]["out_of_range_after_conversion"]
                   + numeric["class_counts"]["other_unparseable"])
            if bad:
                blocking.setdefault("_code", 3)
                blocking["REQUIRED_AGE_PARSE_FAILURE"] = (
                    str(numeric["class_counts"]["non_finite_literal"])
                    + " non-finite, "
                    + str(numeric["class_counts"]["out_of_range_after_conversion"])
                    + " overflow/conversion failures, and "
                    + str(numeric["class_counts"]["other_unparseable"])
                    + " unparseable required_age row(s) in the audit window; "
                    "fail closed instead of silently coercing to missing.")
        for column in ("developer", "publisher"):
            if column in scoped.columns:
                fields[column] = audit_entity_field(frame, column, mask, config)
        if any(column in fields for column in ("developer", "publisher")):
            mark(report, "entities")
        for column in ("platforms", "categories", "genres"):
            if column in scoped.columns:
                fields[column] = audit_multivalue_field(
                    frame, column, mask, config, markers)
        if any(column in fields for column in ("platforms", "categories", "genres")):
            mark(report, "multivalue")
        report["field_audit"] = fields

    pending = sorted(set(pending))
    report["checks"] = {
        "covered": COVERED_CHECKS,
        "not_covered": NOT_COVERED,
        "pending_human_decisions": PENDING_DECISIONS,
        "pending_items_from_this_run": pending,
        "blocking_finding_kinds": sorted(key for key in blocking
                                         if not key.startswith("_")),
        "scope_guards": SCOPE_GUARDS,
    }
    report["run"]["elapsed_seconds"] = None
    if blocking:
        blocking.setdefault("_code", 3)
    return blocking, pending, report


def main(argv=None):
    started = time.perf_counter()
    parser = argparse.ArgumentParser(
        prog="stage0_precheck.py",
        description="Stage-0 read-only precheck of the primary Steam table: "
                    "reads only appid + config.PRIMARY_RAW_COLUMNS, fits "
                    "nothing, installs nothing, writes nothing.")
    parser.add_argument("--input-main", required=True, type=Path,
                        help="Explicit path to the primary table CSV.")
    parser.add_argument("--tree", required=True, choices=("xgb", "rf"),
                        help="Dependency branch for this precheck only. No "
                             "default, no fallback to the other family.")
    parser.add_argument("--encoding", default="utf-8-sig",
                        help="Declared CSV encoding, used strictly with no "
                             "auto-detection or fallback. Optional addition to "
                             "the H04 CLI spec that keeps encoding a human "
                             "declaration.")
    args = parser.parse_args(argv)

    report = {
        "schema": "stage0_precheck.h04_r4",
        "baseline_schema": "stage0_precheck.h04_gpt_r3",
        "completed_stages": [],
        "run": {
            "input_main": str(args.input_main),
            "encoding_declared": args.encoding,
            "tree_branch_requested": args.tree,
            "tree_family_frozen_by_this_run": False,
        },
        "reporting_policy": {
            "output": "one JSON object on stdout; diagnostics on stderr",
            "unavailable_values": "null plus an explicit status string",
            "aggregates_only": "no game names, no raw token lists, no "
                               "row-level identifiers; header names are schema "
                               "metadata, not row content",
        },
        "exit_code_meanings": EXIT_CODE_MEANINGS,
    }
    try:
        blocking, pending, report = run(args, report)
        code = choose_exit_code(blocking, pending + PENDING_DECISIONS)
        report["status"] = "BLOCKED" if blocking else "COMPLETED"
        report["verdict"] = (
            "PRECHECK_BLOCKED" if blocking else
            "NO_DATA_BLOCKER_WITH_OPEN_ITEMS" if code == 4 else
            "NO_DATA_BLOCKER_NO_OPEN_ITEMS")
        if blocking:
            report["blocking_findings"] = {key: value for key, value in
                                           blocking.items()
                                           if not key.startswith("_")}
        report["run"]["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        report["statement"] = (
            "Only checks marked completed_this_run were run. Not a full-"
            "pipeline GO, not a freeze, not execution authorisation.")
        print("[stage0_precheck] status=" + report["status"]
              + " verdict=" + report["verdict"]
              + " exit=" + str(code), file=sys.stderr)
        return emit(report, code)
    except Blocked as exc:
        report["status"] = "BLOCKED"
        report["verdict"] = "PRECHECK_BLOCKED"
        report["blocking_findings"] = exc.finding
        report["checks"] = {"covered": COVERED_CHECKS,
                            "not_covered": NOT_COVERED,
                            "pending_human_decisions": PENDING_DECISIONS,
                            "scope_guards": SCOPE_GUARDS}
        report["run"]["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        print("[stage0_precheck] blocked: " + str(exc.finding), file=sys.stderr)
        return emit(report, exc.code)
    except Exception as exc:
        report["status"] = "INTERNAL_ERROR"
        report["verdict"] = "PRECHECK_FAILED_TO_RUN"
        report["blocking_findings"] = {
            type(exc).__name__: str(exc)[:400],
            "traceback_tail": traceback.format_exc().splitlines()[-3:],
        }
        report["run"]["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        print("[stage0_precheck] internal error: " + repr(exc), file=sys.stderr)
        return emit(report, 5)


if __name__ == "__main__":
    raise SystemExit(main())