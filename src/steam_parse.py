"""Literal, fail-closed parsing for the adopted ``steam-parse/v1`` policy.

This module never locates source data, drops records, imputes, fits, or writes
handoff artifacts.  Invalid values retain their raw spelling and an error;
source missing values retain a separate class.  Historical H04 code is untouched.
"""

from __future__ import annotations

import csv
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import sys
from threading import RLock
from typing import Iterable, Mapping
import unicodedata

import config


_CSV_FIELD_LIMIT_LOCK = RLock()


@contextmanager
def csv_field_limit():
    """Read long literal fields without retaining a process-wide CSV setting.

    The contract has no 128-KiB text limit. Use the platform's accepted integer
    bound; older CSV runtimes may require a smaller C integer than sys.maxsize.
    Serialize project readers because csv.field_size_limit is process-wide.
    """
    with _CSV_FIELD_LIMIT_LOCK:
        previous = csv.field_size_limit()
        limit = sys.maxsize
        try:
            while True:
                try:
                    csv.field_size_limit(max(previous, limit))
                    break
                except OverflowError:
                    limit //= 2
            yield
        finally:
            csv.field_size_limit(previous)


@dataclass(frozen=True)
class ParsedValue:
    raw: str
    value: object
    source_class: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    state: str | None = None

    @property
    def valid(self) -> bool:
        return not self.errors


def _literal(raw: str) -> str:
    if not isinstance(raw, str):
        raise TypeError("Parser inputs must be literal strings")
    return raw


def missing_class(raw: str, field: str) -> str:
    """Classify before conversion; sequence missing words are token-scoped."""
    text = _literal(raw)
    if text == "":
        return "MISSING_EMPTY"
    stripped = text.strip()
    if stripped == "":
        return "MISSING_WHITESPACE"
    policy = config.DATA_PARSE_POLICY
    if field not in policy["missing"]["token_fields"]:
        return "PRESENT"
    declared = {word.lower() for word in policy["missing"]["tokens"]}
    if field in policy["sequences"]["fields"]:
        tokens = [part.strip() for part in text.split(policy["sequences"]["delimiter"])]
        nonempty = [part for part in tokens if part]
        if nonempty and all(part.lower() in declared for part in nonempty):
            return "MISSING_DECLARED"
    elif stripped.lower() in declared:
        return "MISSING_DECLARED"
    return "PRESENT"


def _magnitude(digits: str) -> str:
    """Decimal magnitude without int()/float() or Python's digit-count limit."""
    ascii_digits = "".join(str(unicodedata.decimal(char)) for char in digits)
    return ascii_digits.lstrip("0") or "0"


def _above_bound(magnitude: str, maximum: int) -> bool:
    limit = str(maximum)
    return len(magnitude) > len(limit) or (
        len(magnitude) == len(limit) and magnitude > limit
    )


def parse_appid(raw: str) -> ParsedValue:
    original = _literal(raw)
    source = missing_class(original, "appid")
    if source != "PRESENT":
        return ParsedValue(original, None, source, ("APPID_MISSING",))
    text = original.strip()
    policy = config.DATA_PARSE_POLICY["appid"]
    if re.fullmatch(policy["pattern"], text) is None:
        return ParsedValue(original, None, "INVALID", ("ERR_APPID_ILLEGAL",))
    if _above_bound(_magnitude(text), policy["maximum"]):
        return ParsedValue(original, None, "INVALID", ("ERR_APPID_OUT_OF_INT64",))
    warnings = ("WARN_LEADING_ZERO",) if len(text) > 1 and text[0] == "0" else ()
    return ParsedValue(original, text, "PRESENT", warnings=warnings)


def parse_english(raw: str) -> ParsedValue:
    original = _literal(raw)
    source = missing_class(original, "english")
    if source != "PRESENT":
        return ParsedValue(original, None, source)
    text = original.strip()
    if text not in config.DATA_PARSE_POLICY["english"]["literals"]:
        return ParsedValue(original, None, "INVALID", ("ERR_ENGLISH_ILLEGAL",))
    return ParsedValue(original, int(text), "PRESENT")


_FINITE_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_NON_FINITE = re.compile(r"[+-]?(?:inf|infinity)", re.IGNORECASE)


def parse_age(raw: str) -> ParsedValue:
    original = _literal(raw)
    source = missing_class(original, "required_age")
    if source != "PRESENT":
        return ParsedValue(original, None, source)
    text = original.strip()
    policy = config.DATA_PARSE_POLICY["required_age"]
    if _NON_FINITE.fullmatch(text):
        error = "ERR_AGE_NON_FINITE"
    elif re.fullmatch(policy["pattern"], text) is None:
        error = "ERR_AGE_NON_INTEGER" if _FINITE_DECIMAL.fullmatch(text) else "ERR_AGE_UNPARSEABLE"
    else:
        digits = text[1:] if text[0] in "+-" else text
        magnitude = _magnitude(digits)
        if text.startswith("-") and magnitude != "0":
            error = "ERR_AGE_NEGATIVE"
        elif _above_bound(magnitude, policy["storage_maximum"]):
            error = "ERR_AGE_OUT_OF_INT64"
        else:
            # Magnitude is at most 19 ASCII digits, including long zero prefixes.
            return ParsedValue(original, int(magnitude), "PRESENT")
    return ParsedValue(original, None, "INVALID", (error,))


def parse_sequence(raw: str, field: str) -> ParsedValue:
    original = _literal(raw)
    policy = config.DATA_PARSE_POLICY["sequences"]
    if field not in policy["fields"]:
        raise ValueError(f"Not an adopted sequence field: {field}")
    source = missing_class(original, field)
    if source != "PRESENT":
        return ParsedValue(original, None, source, state="S_MISSING")
    declared = {word.lower() for word in config.DATA_PARSE_POLICY["missing"]["tokens"]}
    result = []
    seen = set()
    for part in original.split(policy["delimiter"]):
        token = part.strip()
        if not token or token.lower() in declared or token in seen:
            continue
        result.append(token)
        seen.add(token)
    suspect = "," in original or "|" in original
    if suspect:
        warning = "WARN_SUSPECT_DELIMITER_PRESENT" if field in ("developer", "publisher") else "WARN_MIXED_DELIMITER"
        warnings = (warning,)
    else:
        warnings = ()
    state = "S_LIST" if result else "S_EMPTY_LIST"
    return ParsedValue(original, tuple(result), "PRESENT", warnings=warnings, state=state)


def sequence_features(parsed: ParsedValue, field: str) -> dict:
    """Derive counts/flags while preserving the source value and source state."""
    if field not in config.DATA_PARSE_POLICY["sequences"]["fields"]:
        raise ValueError(f"Not an adopted sequence field: {field}")
    if not parsed.valid:
        raise ValueError("Cannot derive features from an invalid sequence")
    values = () if parsed.value is None else parsed.value
    if not isinstance(values, tuple) or any(not isinstance(item, str) for item in values):
        raise TypeError("Sequence features require a parsed tuple or source missing")
    result = {}
    count_names = {"platforms": "platform_count", "categories": "category_count", "genres": "genre_count"}
    if field in count_names:
        result[count_names[field]] = len(values)
    if field == "platforms":
        folded = {item.casefold() for item in values}
        for token in config.DATA_PARSE_POLICY["platform_membership"]["tokens"]:
            result[f"has_{token}"] = token.casefold() in folded
    return result


def sequence_diagnostics(parsed: ParsedValue, field: str) -> dict:
    """Label-free accounting; bracket/unknown tokens never change parsing."""
    if field not in config.DATA_PARSE_POLICY["sequences"]["fields"]:
        raise ValueError(f"Not an adopted sequence field: {field}")
    if not parsed.valid:
        raise ValueError("Cannot diagnose an invalid parsed sequence")
    text = parsed.raw.strip()
    result = {
        "rows_wrapped_in_brackets": int(text.startswith("[") and text.endswith("]")),
        "rows_with_alternate_delimiter": int("," in parsed.raw or "|" in parsed.raw),
        # No vocabulary is adopted for entity/category/genre fields.
        "unknown_tokens": None,
    }
    if field == "platforms":
        known = {token.casefold() for token in config.DATA_PARSE_POLICY["platform_membership"]["tokens"]}
        values = () if parsed.value is None else parsed.value
        result["unknown_tokens"] = tuple(token for token in values if token.casefold() not in known)
    return result


def parse_rating(raw: str) -> ParsedValue:
    original = _literal(raw)
    text = original.strip()
    policy = config.DATA_PARSE_POLICY["ratings"]
    source = missing_class(original, "positive_ratings")
    if re.fullmatch(policy["pattern"], text) is None:
        return ParsedValue(original, None, source if source != "PRESENT" else "INVALID", ("RATINGS_ILLEGAL_LITERAL",))
    magnitude = _magnitude(text)
    if _above_bound(magnitude, policy["maximum"]):
        return ParsedValue(original, None, "INVALID", ("RATINGS_OUT_OF_RANGE",))
    return ParsedValue(original, int(magnitude), "PRESENT")


def parse_ratings(positive_raw: str, negative_raw: str) -> ParsedValue:
    positive = parse_rating(positive_raw)
    negative = parse_rating(negative_raw)
    original = json.dumps({"positive_ratings": positive_raw, "negative_ratings": negative_raw}, ensure_ascii=False, separators=(",", ":"))
    errors = tuple(dict.fromkeys(positive.errors + negative.errors))
    if errors:
        return ParsedValue(original, None, "INVALID", errors)
    maximum = config.DATA_PARSE_POLICY["ratings"]["maximum"]
    if negative.value > maximum - positive.value:
        return ParsedValue(original, None, "INVALID", ("RATINGS_SUM_OVERFLOW",))
    return ParsedValue(original, positive.value + negative.value, "PRESENT")


def parse_date(raw: str) -> ParsedValue:
    """The unchanged UTC/coerce/mixed rule; NaT is diagnostic, not deletion."""
    import pandas as pd

    original = _literal(raw)
    result = pd.to_datetime(original, utc=config.RELEASE_DATE_UTC,
                            errors=config.RELEASE_DATE_ERRORS,
                            format=config.RELEASE_DATE_FORMAT)
    if pd.isna(result):
        return ParsedValue(original, None, missing_class(original, "release_date"), warnings=("DATE_NAT",))
    return ParsedValue(original, result, "PRESENT")


def audit_keys(rows: Iterable[Mapping[str, str]], key_column: str = "appid") -> dict:
    """Audit one table independently; do not deduplicate or silently pick rows."""
    raw_values = [row[key_column] for row in rows]
    parsed = [parse_appid(raw) for raw in raw_values]
    groups = {}
    for index, raw in enumerate(raw_values):
        # Raw/strip collisions are independent of lexical validity.  A malformed
        # repeated key retains both its lexical error and its duplicate error.
        groups.setdefault(raw.strip(), []).append(index)
    duplicate_keys = sorted(key for key, indexes in groups.items() if len(indexes) > 1)
    collision_count = sum(len({raw_values[i] for i in groups[key]}) > 1 for key in duplicate_keys)
    for key in duplicate_keys:
        for index in groups[key]:
            errors = parsed[index].errors + ("ERR_APPID_NORMALISATION_COLLISION",)
            parsed[index] = replace(parsed[index], errors=errors)
    invalid_rows = [index + 1 for index, value in enumerate(parsed) if not value.valid]
    return {
        "parsed": parsed,
        "raw_cardinality": len(set(raw_values)),
        "strip_cardinality": len({raw.strip() for raw in raw_values}),
        "duplicate_keys": duplicate_keys,
        "strip_collision_count": collision_count,
        "invalid_rows": invalid_rows,
        "blocking": bool(invalid_rows),
    }


def literal_csv(path: str | Path) -> list[dict[str, str]]:
    """Read UTF-8 CSV records as strings, rejecting malformed table shape."""
    with Path(path).open("r", encoding="utf-8", newline="") as stream, csv_field_limit():
        reader = csv.reader(stream, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("CSV requires a header") from exc
        except csv.Error as exc:
            raise ValueError(f"Malformed CSV header: {exc}") from exc
        if not header or any(not name.strip() or name.startswith("\ufeff") for name in header):
            raise ValueError("CSV header contains an empty name or UTF-8 BOM")
        if len(set(header)) != len(header):
            raise ValueError("CSV header contains duplicate names")
        records = []
        try:
            for source_row_no, row in enumerate(reader, 1):
                if len(row) != len(header):
                    raise ValueError(f"CSV record {source_row_no} has {len(row)} fields; expected {len(header)}")
                records.append(dict(zip(header, row)))
        except csv.Error as exc:
            raise ValueError(f"Malformed CSV record: {exc}") from exc
    return records
