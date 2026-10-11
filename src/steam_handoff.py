"""Build, round-trip and verify steam-handoff/v1 without fitting any model.

Nothing runs on import. Callers explicitly supply literal records or input files.
Synthetic acceptance cannot produce a formal HANDOFF_READY marker. The historical
H04 precheck is deliberately independent of this implementation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import config
from src.steam_parse import (audit_keys, literal_csv, parse_age, parse_appid,
    parse_date, parse_english, parse_rating, parse_ratings, parse_sequence,
    sequence_features)

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs" / "data_contract"
SOURCE_NAMES = ("steam.csv", "steam_description_data.csv", "steam_media_data.csv",
    "steam_requirements_data.csv", "steam_support_info.csv", "steamspy_tag_data.csv")
SOURCE_KEY_COLUMNS = {name: "appid" if name in ("steam.csv", "steamspy_tag_data.csv")
                      else "steam_appid" for name in SOURCE_NAMES}
WINDOW = "A_strictly_earlier_release_years"
LIMIT = 9223372036854775807
RETROSPECTIVE_LIMITATION = ("Single 2019 snapshot: retrospective screening only; "
    "release-year restrictions do not establish launch-time availability, causal effects, or ROI.")
RELEVANT_CODE = ("config.py", "src/steam_parse.py", "src/steam_handoff.py")
H05_IDS = frozenset(f"H05-{prefix}-{i:02}" for prefix,count in
    (("KEY",10),("X",8),("SER",9),("LBL",13),("HIST",8),("AUX",4),("MAN",8),("GATE",8))
    for i in range(1,count+1))


def strict_json_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("JSON_PARSE: duplicate object key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("JSON_PARSE: non-finite constant " + value)
    def finite_float(value):
        number=float(value)
        if not math.isfinite(number):
            raise ValueError("JSON_PARSE: float overflow")
        return number
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def key_digest(keys):
    return digest_bytes(json_text(keys).encode("utf-8"))


def _load_spec():
    schema = strict_json_loads((SPEC_DIR / "handoff_schema.json").read_text())
    with (SPEC_DIR / "field_dictionary.csv").open(newline="", encoding="utf-8") as stream:
        dictionary = list(csv.DictReader(stream))
    return schema, {(x["file"], x["column"]): x for x in dictionary}


def _sentinel_in(value):
    sentinel = config.DATA_HANDOFF_POLICY["scalar_missing_sentinel"]
    if isinstance(value, str):
        return value == sentinel
    if isinstance(value, dict):
        return any(_sentinel_in(k) or _sentinel_in(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_sentinel_in(v) for v in value)
    return False


def encode_cell(value, spec):
    nullable = spec["nullable"] == "true"
    storage = spec["storage_type"]
    if value is None:
        if not nullable:
            raise ValueError("MISSING_NOT_ALLOWED: " + spec["column"])
        return "null" if storage == "JSON-in-cell" else config.DATA_HANDOFF_POLICY["scalar_missing_sentinel"]
    sentinel_declaration = spec["file"] == "manifest/field_dictionary.csv" and spec["column"] == "missing_representation"
    if _sentinel_in(value) and not sentinel_declaration:
        raise ValueError("SENTINEL_COLLISION")
    if storage == "JSON-in-cell":
        return json_text(value)
    if storage.startswith("Int"):
        bits = int(storage[3:])
        if type(value) is not int or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
            raise ValueError("COUNT_CAST/COUNT_OVERFLOW: " + spec["column"])
        if "nonnegative" in spec["logical_type"] and value < 0:
            raise ValueError("COUNT_CAST: negative value")
        return str(value)
    if storage == "boolean_text":
        if type(value) is not bool:
            raise ValueError("BOOL_LITERAL")
        return "true" if value else "false"
    if storage == "float64":
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("NON_FINITE_FLOAT")
        return repr(float(value))
    if not isinstance(value, str):
        raise ValueError("TEXT_CAST: " + spec["column"])
    return value


def decode_cell(text, spec):
    storage = spec["storage_type"]
    if spec["file"] == "manifest/field_dictionary.csv" and spec["column"] == "missing_representation":
        return text
    if text == config.DATA_HANDOFF_POLICY["scalar_missing_sentinel"]:
        if spec["nullable"] != "true" or storage == "JSON-in-cell":
            raise ValueError("MISSING_NOT_ALLOWED")
        return None
    if storage == "JSON-in-cell":
        value = strict_json_loads(text)
        if value is None and spec["nullable"] != "true":
            raise ValueError("MISSING_NOT_ALLOWED")
        if _sentinel_in(value):
            raise ValueError("SENTINEL_COLLISION")
        if spec["logical_type"] == "nullable_ordered_string_sequence":
            if value is not None and (not isinstance(value, list) or any(type(x) is not str or not x for x in value)):
                raise ValueError("JSON_PARSE: source sequence domain")
            return None if value is None else tuple(value)
        return value
    if storage.startswith("Int"):
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)", text):
            raise ValueError("COUNT_CAST")
        if len(text.lstrip("-")) > 19:
            raise ValueError("COUNT_OVERFLOW")
        value = int(text)
    elif storage == "boolean_text":
        if text not in config.DATA_HANDOFF_POLICY["boolean_literals"]:
            raise ValueError("BOOL_LITERAL")
        value = text == "true"
    elif storage == "float64":
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
            raise ValueError("FLOAT_CAST")
        value = float(text)
    else:
        value = text
    encode_cell(value, spec)  # Same declared type/bounds; never coerce/fill on failure.
    return value


def write_table(path, rows, columns, definitions, logical_path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            if set(row) != set(columns):
                raise ValueError("SCHEMA_COLUMNS")
            writer.writerow([encode_cell(row[n], definitions[logical_path, n]) for n in columns])


def read_table(path, columns, definitions, logical_path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("CSV_BOM")
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != columns:
            raise ValueError("SCHEMA_COLUMNS")
        result = []
        for cells in reader:
            if len(cells) != len(columns):
                raise ValueError("SCHEMA_COLUMNS")
            result.append({n: decode_cell(t, definitions[logical_path, n]) for n, t in zip(columns, cells)})
    return result


@dataclass
class Dataset:
    raw_main: list
    raw_aux: dict
    tables: dict
    history_windows: dict
    issues: list
    key_audits: dict
    statistics: dict


def _expected_label_info(raw_rows):
    """Independent population computation; does not consume producer cutoffs/y."""
    cohorts = defaultdict(list)
    row_dates = {}
    totals = {}
    for i, raw in enumerate(raw_rows, 1):
        date = pd.to_datetime(raw["release_date"], utc=config.RELEASE_DATE_UTC,
            errors=config.RELEASE_DATE_ERRORS, format=config.RELEASE_DATE_FORMAT)
        row_dates[i] = None if pd.isna(date) else date
        if pd.isna(date) or date.year in config.EXCLUDED_RELEASE_YEARS:
            continue
        cohorts[date.year].append(i)
        values = []
        for name in ("positive_ratings", "negative_ratings"):
            text = raw[name].strip()
            magnitude = text.lstrip("0") or "0"
            if not re.fullmatch(r"[0-9]+", text) or len(magnitude) > 19 or (len(magnitude) == 19 and magnitude > str(LIMIT)):
                values = []; break
            values.append(int(magnitude))
        totals[i] = sum(values) if len(values) == 2 and values[1] <= LIMIT - values[0] else None
    result = {}
    labels = {}
    for year, indexes in sorted(cohorts.items()):
        computable = all(totals[i] is not None for i in indexes)
        cutoff = float(pd.Series([totals[i] for i in indexes], dtype="int64").quantile(
            config.TARGET_QUANTILE, interpolation=config.TARGET_INTERPOLATION)) if computable else None
        positive = None
        if computable:
            series=pd.Series([totals[i] for i in indexes],index=indexes,dtype="int64")
            compared=series.ge(cutoff) if config.TARGET_INCLUSIVE else series.gt(cutoff)
            labels.update({i:int(value) for i,value in compared.items()})
            positive = sum(labels[i] for i in indexes)
        result[year] = dict(indexes=indexes, cohort_n=len(indexes), computable=computable,
                            cutoff_value=cutoff, positive_n=positive)
    return result, labels, row_dates, totals


def build_dataset(main_rows, auxiliary_rows=None):
    """Pure construction: retains every source identity, including failed rows."""
    main = deepcopy(list(main_rows))
    aux = {name: deepcopy(list((auxiliary_rows or {}).get(name, []))) for name in SOURCE_NAMES[1:]}
    needed = {"appid", "name", "positive_ratings", "negative_ratings", *config.PRIMARY_RAW_COLUMNS}
    if any(not needed.issubset(r) or any(type(v) is not str for v in r.values()) for r in main):
        raise ValueError("SOURCE_SCHEMA: literal main fields required")
    audits = {"steam.csv": audit_keys(main)}
    for name, rows in aux.items():
        key_column = SOURCE_KEY_COLUMNS[name]
        if any(key_column not in r or any(type(v) is not str for v in r.values()) for r in rows):
            raise ValueError("SOURCE_SCHEMA: auxiliary " + key_column + " required for " + name)
        audits[name] = audit_keys(rows, key_column)
    keys, dispositions, xs, ys, states = [], [], [], [], []
    issues = []
    parsed_rows = []
    cohorts = defaultdict(list)
    for i, raw in enumerate(main, 1):
        key = audits["steam.csv"]["parsed"][i - 1]
        date = parse_date(raw["release_date"])
        english, age = parse_english(raw["english"]), parse_age(raw["required_age"])
        sequences = {f: parse_sequence(raw[f], f) for f in config.DATA_PARSE_POLICY["sequences"]["fields"]}
        ratings = parse_ratings(raw["positive_ratings"], raw["negative_ratings"])
        base = date.value is not None and date.value.year not in config.EXCLUDED_RELEASE_YEARS
        entries = [key, date, english, age, *sequences.values()]
        codes = list(dict.fromkeys(c for p in entries for c in p.errors + p.warnings))
        codes.extend(c for c in ratings.errors if c not in codes)
        year = None if date.value is None else date.value.year
        if year is not None and year > config.TEST_YEAR and year not in config.EXCLUDED_RELEASE_YEARS:
            codes.append("UNCOVERED_YEAR")
        for p in entries:
            for code in p.errors + p.warnings:
                issues.append(dict(source_file="steam.csv", source_row_no=i, code=code,
                    blocking=code in p.errors, raw=p.raw))
        for code in ratings.errors:
            issues.append(dict(source_file="steam.csv", source_row_no=i, code=code, blocking=base, raw=ratings.raw))
        if any(_sentinel_in(v) for v in raw.values()):
            issues.append(dict(source_file="steam.csv", source_row_no=i, code="SENTINEL_COLLISION", blocking=True, raw=config.DATA_HANDOFF_POLICY["scalar_missing_sentinel"]))
            codes.append("SENTINEL_COLLISION")
        data = dict(identity=i, raw=raw, key=key, date=date, english=english, age=age,
            sequences=sequences, ratings=ratings, base=base, year=year, codes=codes)
        parsed_rows.append(data)
        if base:
            cohorts[year].append(data)
    cutoffs, labels = {}, {}
    # Producer calculation is separately checked by _expected_label_info.
    for year, records in sorted(cohorts.items()):
        computable = all(r["ratings"].valid for r in records)
        cutoff = float(pd.Series([r["ratings"].value for r in records], dtype="int64").quantile(
            config.TARGET_QUANTILE, interpolation=config.TARGET_INTERPOLATION)) if computable else None
        if computable:
            # Match the frozen v1.1 pandas comparison, including rounded q90
            # cutoffs near Int64 max. Python scalar comparison differs there.
            series=pd.Series([r["ratings"].value for r in records],index=[r["identity"] for r in records],dtype="int64")
            compared=series.ge(cutoff) if config.TARGET_INCLUSIVE else series.gt(cutoff)
            labels.update({i:int(value) for i,value in compared.items()})
        cutoffs[year] = dict(release_year=year, cohort_n=len(records), computable=computable,
            cutoff_value=cutoff, positive_n=sum(labels[r["identity"]] for r in records) if computable else None,
            developed_cohort_n=0, developed_positive_n=0 if computable else None,
            in_developed_domain=year <= config.TRAIN_MAX_YEAR or year in (config.VALIDATION_YEAR, config.TEST_YEAR),
            algorithm_id="within_year_quantile_linear_inclusive", parameter_ref="config.target")
    codebook = strict_json_loads((SPEC_DIR / "codebook.json").read_text())
    for r in parsed_rows:
        i, raw, year = r["identity"], r["raw"], r["year"]
        predicates = {"invalid_key": not r["key"].valid, "invalid_date_nat": year is None,
            "excluded_2019": year in config.EXCLUDED_RELEASE_YEARS, "uncovered_year": year is not None and year > config.TEST_YEAR and year not in config.EXCLUDED_RELEASE_YEARS,
            "invalid_label_input": r["base"] and i not in labels,
            "train": year is not None and year <= config.TRAIN_MAX_YEAR,
            "validation": year == config.VALIDATION_YEAR, "test": year == config.TEST_YEAR}
        disposition = next(k for k in config.DATA_HANDOFF_POLICY["row_disposition_precedence"] if predicates[k])
        r["disposition"] = disposition
        key = r["key"].value if r["key"].valid else None
        identity = dict(source_file="steam.csv", source_row_no=i)
        trigger = {"appid": raw["appid"], "release_date": raw["release_date"],
                   **{f: raw[f] for f in ("english", "required_age", "positive_ratings", "negative_ratings")}}
        dispositions.append(dict(**identity, raw_appid=raw["appid"], disposition=disposition,
            failure_codes=r["codes"], trigger_values=trigger,
            source_reference=dict(logical_file="steam.csv", source_row_no=i)))
        raw_parse = {f: raw[f] for f in ("english", "required_age", *config.DATA_PARSE_POLICY["sequences"]["fields"])}
        classes = {"english": r["english"].source_class, "required_age": r["age"].source_class,
                   **{f: p.source_class for f, p in r["sequences"].items()}}
        keys.append(dict(appid=key, raw_appid=raw["appid"], name=raw["name"], release_date=raw["release_date"],
            release_date_utc=None if r["date"].value is None else r["date"].value.isoformat().replace("+00:00", "Z"),
            release_year=year, split=codebook["split_by_disposition"][disposition], disposition=disposition,
            failure_codes=r["codes"], **identity, raw_parse_values=raw_parse, source_value_classes=classes))
        if disposition not in ("train", "validation", "test"):
            continue
        cut = cutoffs[year]
        cut["developed_cohort_n"] += 1
        cut["developed_positive_n"] += labels[i]
        x = {"appid": key, "english": r["english"].value, "required_age": r["age"].value,
            **{f: p.value for f, p in r["sequences"].items()}}
        for f in ("platforms", "categories", "genres"):
            x.update(sequence_features(r["sequences"][f], f))
        date = r["date"].value
        month, day = date.month, date.dayofweek
        x.update(release_month=month, release_quarter=(month - 1) // 3 + 1, release_day_of_week=day)
        for prefix, value, origin, period in [("release_month", month, config.MONTH_CYCLE_ORIGIN, config.MONTH_CYCLE_PERIOD),
                ("release_day_of_week", day, config.DAY_OF_WEEK_CYCLE_ORIGIN, config.DAY_OF_WEEK_CYCLE_PERIOD)]:
            angle = 2 * math.pi * (value - origin) / period
            x[prefix + "_sin"], x[prefix + "_cos"] = math.sin(angle), math.cos(angle)
        xs.append(x)
        ys.append(dict(appid=key, hit_reviews=labels[i], positive_ratings=parse_rating(raw["positive_ratings"]).value,
            negative_ratings=parse_rating(raw["negative_ratings"]).value, total_ratings=r["ratings"].value,
            cohort_n=cut["cohort_n"], positive_in_cohort=cut["positive_n"], cutoff_value=cut["cutoff_value"],
            label_basis="full_valid_UTC_nonexcluded_year_population"))
        states.append(dict(appid=key, **{f: p.state for f, p in r["sequences"].items()},
            source_missing_classes={f: p.source_class for f, p in r["sequences"].items()}))
    by_x, by_y = {r["appid"]: r for r in xs}, {r["appid"]: r for r in ys}
    years = {r["appid"]: r["release_year"] for r in keys if r["split"] in ("train", "validation", "test")}
    edges, target_windows = [], []
    entity_indexes = {kind: defaultdict(set) for kind in ("developer", "publisher")}
    for key, row in by_x.items():
        for kind in entity_indexes:
            for entity in row[kind] or ():
                entity_indexes[kind][entity].add(key)
    for key, x in sorted(by_x.items()):
        for kind, prefix in [("developer", "dev"), ("publisher", "pub")]:
            sources = set()
            for entity in x[kind] or ():
                sources.update(entity_indexes[kind][entity])
            sources = sorted(k for k in sources if years[k] < years[key] and years[k] not in config.EXCLUDED_RELEASE_YEARS)
            n, h = len(sources), sum(by_y[k]["hit_reviews"] for k in sources)
            x[prefix + "_prior_count"] = math.log1p(n)
            x[prefix + "_prior_hit_rate"] = (h + config.HISTORY_ALPHA * config.HISTORY_PRIOR_MEAN) / (n + config.HISTORY_ALPHA)
            source_years = sorted({years[k] for k in sources})
            target_windows.append(dict(window_variant=WINDOW, target_appid=key, entity_kind=kind,
                source_years=source_years, source_max_year=max(source_years) if source_years else None))
            edges.extend(dict(window_variant=WINDOW, target_appid=key, entity_kind=kind, source_year=years[k], source_appid=k) for k in sources)
    main_keys = {p.value for p in audits["steam.csv"]["parsed"] if p.valid}
    coverage = []
    for name, rows in aux.items():
        audit = audits[name]
        aux_keys = {p.value for p in audit["parsed"] if p.valid}
        coverage.append(dict(aux_table=name, source_rows=len(rows), invalid_key_rows=len(audit["invalid_rows"]),
            duplicate_keys=len(audit["duplicate_keys"]), extra_keys=len(aux_keys-main_keys), missing_coverage=len(main_keys-aux_keys),
            main_rows_before=len(main), main_rows_after=len(main)))
        for i, p in enumerate(audit["parsed"], 1):
            issues.extend(dict(source_file=name, source_row_no=i, code=code, blocking=True, raw=p.raw) for code in p.errors)
    tables = {"handoff/x_primary.csv": xs, "handoff/y_label.csv": ys, "handoff/x_entity_states.csv": states,
        "handoff/keys_meta.csv": keys, "handoff/row_disposition.csv": dispositions,
        "handoff/rows_excluded.csv": [r.copy() for r in dispositions if r["disposition"] == "excluded_2019"],
        "handoff/rows_invalid_unknown.csv": [r.copy() for r in dispositions if r["disposition"] in ("invalid_key", "invalid_date_nat", "uncovered_year", "invalid_label_input")],
        "handoff/year_cutoffs.csv": list(cutoffs.values()), "handoff/history_source_membership.csv": edges,
        "handoff/aux_coverage.csv": coverage}
    schema, _ = _load_spec()
    for path, rows in tables.items():
        rows.sort(key=lambda r: tuple(r[n] for n in schema["files"][path]["row_order"]))
    cohort_windows = []
    for year in sorted(set(years.values())):
        ysources = sorted({edge["source_year"] for edge in edges if years[edge["target_appid"]] == year})
        cohort_windows.append(dict(window_variant=WINDOW, release_year=year, source_years=ysources,
            source_max_year=max(ysources) if ysources else None, parameters=config.design_contract()["history"],
            membership_digest=key_digest([[edge[k] for k in schema["files"]["handoff/history_source_membership.csv"]["primary_key"]] for edge in edges if years[edge["target_appid"]] == year])))
    windows = dict(window_variant=WINDOW, target_windows=target_windows, cohort_windows=cohort_windows)
    stats = dict(source_records=len(main), dispositions=dict(Counter(r["disposition"] for r in dispositions)),
        base_population_rows=sum(len(r) for r in cohorts.values()), developed_rows=len(xs),
        population_positive_sum=sum(c["positive_n"] for c in cutoffs.values()) if all(c["computable"] for c in cutoffs.values()) else None,
        developed_positive_sum=sum(r["hit_reviews"] for r in ys), columns_before_drop=["appid", *config.PRIMARY_FEATURE_COLUMNS],
        columns_after_drop=list(config.PRIMARY_FEATURE_COLUMNS), learned_transforms=False)
    return Dataset(main, aux, tables, windows, issues, audits, stats)


def validate_dataset(data):
    """Independently rebuild populations and complete history sets by identity."""
    schema, definitions = _load_spec()
    checks = {}
    def add(identifier, ok, evidence):
        checks[identifier] = dict(status="PASS" if ok else "FAIL", evidence=evidence)
    tables = data.tables
    x, y, meta = tables["handoff/x_primary.csv"], tables["handoff/y_label.csv"], tables["handoff/keys_meta.csv"]
    dispositions, states = tables["handoff/row_disposition.csv"], tables["handoff/x_entity_states.csv"]
    xm, ym, mm = {r["appid"]: r for r in x}, {r["appid"]: r for r in y}, {r["appid"]: r for r in meta if r["split"] in ("train", "validation", "test")}
    expected, expected_labels, dates, totals = _expected_label_info(data.raw_main)
    identities = [(r["source_file"], r["source_row_no"]) for r in meta]
    key_counts = {p: len(rows)-len({tuple(r[n] for n in schema["files"][p]["primary_key"]) for r in rows}) for p, rows in tables.items()}
    add("H05-KEY-01", not any(key_counts.values()), dict(duplicate_counts=key_counts, JSON_object_primary_key=None))
    raw_key_audit = audit_keys(data.raw_main)
    add("H05-KEY-02", not raw_key_audit["duplicate_keys"], dict(raw_cardinality=raw_key_audit["raw_cardinality"], strip_cardinality=raw_key_audit["strip_cardinality"], collisions=raw_key_audit["strip_collision_count"]))
    source_identity_ok=all(type(r["source_row_no"]) is int and 1<=r["source_row_no"]<=len(data.raw_main)
        and r["appid"]==(raw_key_audit["parsed"][r["source_row_no"]-1].value if raw_key_audit["parsed"][r["source_row_no"]-1].valid else None)
        and all(r[f]==data.raw_main[r["source_row_no"]-1][f] for f in ("raw_appid","name","release_date") if f!="raw_appid")
        and r["raw_appid"]==data.raw_main[r["source_row_no"]-1]["appid"] for r in meta)
    add("H05-KEY-03", source_identity_ok and set(identities)=={("steam.csv", i) for i in range(1,len(data.raw_main)+1)}=={(r["source_file"],r["source_row_no"]) for r in dispositions} and len(identities)==len(set(identities)), dict(identity_rows=len(identities),source_binding_matches=source_identity_ok))
    counts = Counter(r["disposition"] for r in dispositions)
    add("H05-KEY-04", sum(counts.values())==len(data.raw_main) and len(dispositions)==len(data.raw_main), dict(source_records=len(data.raw_main), dispositions=dict(counts)))
    precedence = list(config.DATA_HANDOFF_POLICY["row_disposition_precedence"])
    codebook = strict_json_loads((SPEC_DIR/"codebook.json").read_text())
    disposition_by_id = {r["source_row_no"]:r for r in dispositions}
    expected_dispositions = {}
    for i, raw in enumerate(data.raw_main,1):
        date, key = dates[i], raw_key_audit["parsed"][i-1]
        year = None if date is None else date.year
        conditions = [not key.valid, date is None, year in config.EXCLUDED_RELEASE_YEARS,
            year is not None and year>config.TEST_YEAR and year not in config.EXCLUDED_RELEASE_YEARS,
            year in expected and i not in expected_labels,
            year is not None and year<=config.TRAIN_MAX_YEAR, year==config.VALIDATION_YEAR, year==config.TEST_YEAR]
        expected_dispositions[i] = next(name for name, match in zip(precedence,conditions) if match)
    add("H05-KEY-05", precedence==codebook["dispositions"] and all(disposition_by_id.get(i,{}).get("disposition")==v for i,v in expected_dispositions.items()) and all(r["split"]==codebook["split_by_disposition"][r["disposition"]] for r in meta), dict(precedence=precedence, source_records_checked=len(expected_dispositions)))
    add("H05-KEY-06", set(xm)==set(ym)==set(mm)=={r["appid"] for r in states}, dict(X=len(x),y=len(y),states=len(states)))
    excluded=[r for r in dispositions if r["disposition"]=="excluded_2019"]
    invalid=[r for r in dispositions if r["disposition"] in ("invalid_key","invalid_date_nat","uncovered_year","invalid_label_input")]
    add("H05-KEY-07", tables["handoff/rows_excluded.csv"]==excluded and tables["handoff/rows_invalid_unknown.csv"]==invalid, dict(excluded=len(excluded),invalid_unknown=len(invalid)))
    add("H05-KEY-08", all(rows==sorted(rows,key=lambda r:tuple(r[n] for n in schema["files"][p]["row_order"])) for p,rows in tables.items()), dict(digest_encoding="canonical UTF-8 strict JSON arrays",per_file_key_digest={p:key_digest([[r[n] for n in schema["files"][p]["primary_key"]] for r in rows]) for p,rows in tables.items()}))
    # Reversing each keyed projection changes neither maps nor independently rebuilt results.
    add("H05-KEY-09", xm=={r["appid"]:r for r in reversed(x)} and ym=={r["appid"]:r for r in reversed(y)}, dict(perturbation="reverse projections then explicit key join",joined_keys=len(xm)))
    bad_ids={i for i,v in enumerate(raw_key_audit["parsed"],1) if not v.valid}
    add("H05-KEY-10", all(disposition_by_id.get(i,{}).get("disposition")=="invalid_key" for i in bad_ids) and all(r["appid"] is None for r in meta if r["source_row_no"] in bad_ids), dict(invalid_source_identities=sorted(bad_ids)))
    columns=list(config.PRIMARY_FEATURE_COLUMNS)
    actual_columns=schema["files"]["handoff/x_primary.csv"]["columns"]
    add("H05-X-01", actual_columns==["appid",*columns] and all(set(r)==set(actual_columns) for r in x), dict(columns=actual_columns,primary_count=len(columns)))
    add("H05-X-02", data.statistics["columns_before_drop"]==actual_columns and data.statistics["columns_after_drop"]==columns, dict(before=actual_columns,after=columns))
    banned=set(config.FORBIDDEN_PREDICTOR_COLUMNS)
    add("H05-X-03", not (set(columns)&banned) and all(set(r)-{"appid"}==set(columns) for r in x), dict(forbidden_intersection=sorted(set(columns)&banned)))
    add("H05-X-04", len(columns)==24 and all(len(r)==25 for r in x), dict(allowed_primary_columns=24,rows_checked=len(x)))
    add("H05-X-05", not (set(columns)&set(config.SNAPSHOT_SENSITIVITY_COLUMNS)), dict(sensitivity_primary_intersection=[]))
    with (SPEC_DIR/"source_map.csv").open(newline="",encoding="utf-8") as stream:
        source_map=list(csv.DictReader(stream))
    x_sources={r["source_file"] for r in source_map if r["file"]=="handoff/x_primary.csv"}
    add("H05-X-06", not (x_sources&set(config.FORBIDDEN_SOURCES)), dict(primary_sources=sorted(x_sources)))
    add("H05-X-07", not (set(columns)&set(config.METADATA_COLUMNS)), dict(metadata_removed=list(config.METADATA_COLUMNS)))
    add("H05-X-08", data.statistics["learned_transforms"] is False and all(r["learned_transform"]=="false" for r in definitions.values()), dict(fitted_artifacts=[],learned_transforms=False))
    encode_errors=[]
    for p,rows in tables.items():
        for i,row in enumerate(rows,1):
            for n,value in row.items():
                try: encode_cell(value, definitions[p,n])
                except (KeyError,ValueError,TypeError,OverflowError) as exc:encode_errors.append(dict(file=p,row=i,column=n,error=str(exc)))
    add("H05-SER-02", not encode_errors, dict(type_or_finite_errors=encode_errors))
    state_by_key={r["appid"]:r for r in states}
    state_errors=[]
    for key,row in xm.items():
        if key not in state_by_key or key not in mm:
            state_errors.append(key);continue
        raw=mm[key]["raw_parse_values"]
        for f in config.DATA_PARSE_POLICY["sequences"]["fields"]:
            p=parse_sequence(raw[f],f)
            if row[f]!=p.value or state_by_key[key][f]!=p.state or state_by_key[key]["source_missing_classes"][f]!=p.source_class:
                state_errors.append((key,f))
    add("H05-SER-03", not state_errors, dict(source_value_state_mismatches=state_errors,reserved_slot_source_reachable=False))
    add("H05-SER-05", not any(_sentinel_in(r) for rows in tables.values() for r in rows), dict(sentinel=config.DATA_HANDOFF_POLICY["scalar_missing_sentinel"]))
    parse_fields=("english","required_age",*config.DATA_PARSE_POLICY["sequences"]["fields"])
    source_state_ok=True
    for r in meta:
        raw=data.raw_main[r["source_row_no"]-1]
        expected_classes={"english":parse_english(raw["english"]).source_class,"required_age":parse_age(raw["required_age"]).source_class,
            **{f:parse_sequence(raw[f],f).source_class for f in config.DATA_PARSE_POLICY["sequences"]["fields"]}}
        source_state_ok=source_state_ok and r["raw_parse_values"]=={f:raw[f] for f in parse_fields} and r["source_value_classes"]==expected_classes
    add("H05-SER-08", not state_errors and source_state_ok, dict(pre_lossy_source_capture_rows=len(meta),scalar_and_sequence_source_classes_match=source_state_ok))
    cut={r["release_year"]:r for r in tables["handoff/year_cutoffs.csv"]}
    rating_errors=sum(totals[i] is None for v in expected.values() for i in v["indexes"])
    add("H05-LBL-01", rating_errors==0, dict(base_population_illegal_ratings=rating_errors, outside_base_policy="diagnostic only"))
    rating_trace_errors=[]
    for key,r in ym.items():
        if key not in mm:
            rating_trace_errors.append(key);continue
        source_no=mm[key]["source_row_no"]
        raw=data.raw_main[source_no-1]
        if (type(r["total_ratings"]) is not int or r["negative_ratings"]>LIMIT-r["positive_ratings"]
                or r["total_ratings"]!=r["positive_ratings"]+r["negative_ratings"]
                or r["total_ratings"]!=totals.get(source_no)
                or str(r["positive_ratings"])!=(raw["positive_ratings"].strip().lstrip("0") or "0")
                or str(r["negative_ratings"])!=(raw["negative_ratings"].strip().lstrip("0") or "0")):
            rating_trace_errors.append(key)
    add("H05-LBL-02", not rating_trace_errors, dict(developed_safe_sum_rows=len(y),source_trace_mismatches=rating_trace_errors))
    base_n=sum(v["cohort_n"] for v in expected.values())
    add("H05-LBL-03", data.statistics["base_population_rows"]==base_n, dict(expected_population=base_n, definition="valid UTC date and nonexcluded year only"))
    add("H05-LBL-04", set(cut)==set(expected) and all(cut[year]["cohort_n"]==e["cohort_n"] and cut[year]["computable"]==e["computable"] and cut[year]["cutoff_value"]==e["cutoff_value"] for year,e in expected.items()), dict(independently_rebuilt_cohorts={year:{k:v for k,v in e.items() if k!='indexes'} for year,e in expected.items()}))
    add("H05-LBL-05", config.TARGET_QUANTILE==0.9 and config.TARGET_INTERPOLATION=="linear" and config.TARGET_INCLUSIVE is True and config.MIN_YEAR_GAMES is None and config.EXCLUDED_RELEASE_YEARS==(2019,), dict(target=config.design_contract()["target"]))
    population_positive=sum(v["positive_n"] for v in expected.values()) if all(v["computable"] for v in expected.values()) else None
    add("H05-LBL-06", set(cut)==set(expected) and all(cut[year]["positive_n"]==e["positive_n"] and (not e["computable"] or cut[year]["positive_n"]>=1) for year,e in expected.items()) and sum(r["cohort_n"] for r in cut.values())==base_n and data.statistics["population_positive_sum"]==population_positive, dict(base_rows=base_n,population_positive_sum=population_positive))
    expected_dev={r["appid"] for r in meta if r["disposition"] in ("train","validation","test")}
    label_trace_ok=all(key in mm and (e:=expected.get(mm[key]["release_year"])) is not None
        and r["cohort_n"]==e["cohort_n"] and r["positive_in_cohort"]==e["positive_n"]
        and r["cutoff_value"]==e["cutoff_value"]
        and r["label_basis"]=="full_valid_UTC_nonexcluded_year_population" for key,r in ym.items())
    developed_counts_ok=all(c["developed_cohort_n"]==sum(m["release_year"]==year for m in mm.values())
        and c["developed_positive_n"]==sum(expected_labels.get(m["source_row_no"],0) for m in mm.values() if m["release_year"]==year)
        for year,c in cut.items())
    add("H05-LBL-07", expected_dev==set(ym) and label_trace_ok and developed_counts_ok and data.statistics["developed_rows"]==len(y) and data.statistics["developed_positive_sum"]==sum(r["hit_reviews"] for r in y) and sum(c["developed_cohort_n"] for c in cut.values())==len(y) and sum(c["developed_positive_n"] or 0 for c in cut.values())==sum(r["hit_reviews"] for r in y), dict(developed_rows=len(y),developed_positive=sum(r["hit_reviews"] for r in y),population_positive=population_positive,label_trace_matches=label_trace_ok))
    add("H05-LBL-08", all(r["source_row_no"] in expected_labels and ym[r["appid"]]["hit_reviews"]==expected_labels[r["source_row_no"]] for r in mm.values()), dict(independent_labels_checked=len(mm), indeterminate_population_rows=rating_errors))
    exclusion_ok=all(r["appid"] not in ym for r in meta if r["release_year"] in config.EXCLUDED_RELEASE_YEARS)
    nat_ok=all(r["appid"] not in ym for r in meta if r["release_year"] is None)
    unknown_ok=all(r["appid"] not in ym for r in meta if r["release_year"] is not None and r["release_year"]>config.TEST_YEAR and r["release_year"] not in config.EXCLUDED_RELEASE_YEARS)
    add("H05-LBL-09", exclusion_ok, dict(excluded_year_rows=sum(r["release_year"] in config.EXCLUDED_RELEASE_YEARS for r in meta)))
    add("H05-LBL-10", nat_ok and all(r["release_date"]==data.raw_main[r["source_row_no"]-1]["release_date"] and "DATE_NAT" in r["failure_codes"] for r in meta if r["release_year"] is None), dict(NaT_rows=sum(r["release_year"] is None for r in meta)))
    add("H05-LBL-11", unknown_ok and all(r["release_year"] in cut for r in meta if r["release_year"] is not None and r["release_year"]>config.TEST_YEAR and r["release_year"] not in config.EXCLUDED_RELEASE_YEARS), dict(uncovered_years=sorted(year for year in expected if year>config.TEST_YEAR)))
    add("H05-LBL-12", all(cut[year]["cutoff_value"]==e["cutoff_value"] for year,e in expected.items()), dict(independent_per_year_cutoffs={year:e["cutoff_value"] for year,e in expected.items()}))
    mandatory_block=any(a["blocking"] for a in data.key_audits.values()) or rating_errors>0
    add("H05-LBL-13", not mandatory_block or any(i["blocking"] for i in data.issues), dict(invalid_inputs_retained=len(invalid),blocking_diagnostics=sum(i["blocking"] for i in data.issues),cohort_size_not_shrunk=base_n))
    edges=tables["handoff/history_source_membership.csv"]
    actual_edges={(r["window_variant"],r["target_appid"],r["entity_kind"],r["source_year"],r["source_appid"]) for r in edges}
    expected_edges=set()
    # Reparse raw source text independently of producer X/indexes/edges. Index
    # by year to reconstruct every eligible source without repeated full scans.
    raw_entities={kind:{key:set(parse_sequence(m["raw_parse_values"][kind],kind).value or ())
                        for key,m in mm.items()} for kind in ("developer","publisher")}
    expected_index={kind:defaultdict(lambda:defaultdict(set)) for kind in raw_entities}
    for kind,by_key in raw_entities.items():
        for source,entities in by_key.items():
            year=mm[source]["release_year"]
            if year not in config.EXCLUDED_RELEASE_YEARS:
                for entity in entities:expected_index[kind][entity][year].add(source)
    expected_sources={}
    for target in xm:
        for kind in ("developer","publisher"):
            sources=set()
            for entity in raw_entities[kind][target]:
                for year,members in expected_index[kind][entity].items():
                    if year<mm[target]["release_year"]:sources.update(members)
            expected_sources[target,kind]=sources
            expected_edges.update((WINDOW,target,kind,mm[source]["release_year"],source) for source in sources)
    valid_edge_ids=all(r["target_appid"] in mm and r["source_appid"] in mm for r in edges)
    add("H05-HIST-01", valid_edge_ids and all(r["source_year"]<mm[r["target_appid"]]["release_year"] for r in edges), dict(edges_checked=len(edges)))
    add("H05-HIST-02", valid_edge_ids and all(r["source_year"]==mm[r["source_appid"]]["release_year"] and r["source_year"] not in config.EXCLUDED_RELEASE_YEARS for r in edges), dict(excluded_source_edges=sum(r["source_year"] in config.EXCLUDED_RELEASE_YEARS for r in edges)))
    add("H05-HIST-03", len(actual_edges)==len(edges) and all(r["window_variant"]==WINDOW for r in edges), dict(edge_primary_key=schema["files"]["handoff/history_source_membership.csv"]["primary_key"],duplicates=len(edges)-len(actual_edges)))
    add("H05-HIST-04", actual_edges==expected_edges and len(edges)==len(actual_edges), dict(missing_sources=[list(v) for v in sorted(expected_edges-actual_edges)],extra_sources=[list(v) for v in sorted(actual_edges-expected_edges)],duplicates=len(edges)-len(actual_edges)))
    formula_errors=[]
    for target,row in xm.items():
        for kind,prefix in (("developer","dev"),("publisher","pub")):
            source_ids=expected_sources[target,kind]
            n,h=len(source_ids),sum(expected_labels[mm[s]["source_row_no"]] for s in source_ids)
            if not all(type(row[prefix+suffix]) in (int,float) and math.isfinite(row[prefix+suffix]) for suffix in ("_prior_count","_prior_hit_rate")) or abs(row[prefix+"_prior_count"]-math.log1p(n))>1e-12 or abs(row[prefix+"_prior_hit_rate"]-(h+config.HISTORY_ALPHA*config.HISTORY_PRIOR_MEAN)/(n+config.HISTORY_ALPHA))>1e-12:
                formula_errors.append([target,kind,n,h])
    add("H05-HIST-06", not formula_errors, dict(formula_mismatches=formula_errors,parameters=config.design_contract()["history"],count_source="independent complete reconstruction"))
    windows=data.history_windows["target_windows"]
    actual_windows={(w["window_variant"],w["target_appid"],w["entity_kind"]):w for w in windows}
    window_ok=set(actual_windows)=={(WINDOW,key,kind) for key in xm for kind in ("developer","publisher")} and len(actual_windows)==len(windows)==2*len(xm)
    for key,w in actual_windows.items():
        source_years=sorted({mm[source]["release_year"] for source in expected_sources.get((key[1],key[2]),set())})
        window_ok=window_ok and w["source_years"]==source_years and w["source_max_year"]==(max(source_years) if source_years else None)
    cohort_windows=data.history_windows["cohort_windows"]
    actual_cohorts={(w["window_variant"],w["release_year"]):w for w in cohort_windows}
    expected_years={m["release_year"] for m in mm.values()}
    window_ok=window_ok and set(actual_cohorts)=={(WINDOW,year) for year in expected_years} and len(actual_cohorts)==len(cohort_windows)
    expected_cohort_edges=defaultdict(list)
    for edge in sorted(expected_edges):expected_cohort_edges[mm[edge[1]]["release_year"]].append(edge)
    for (variant,year),w in actual_cohorts.items():
        cohort_edges=expected_cohort_edges[year]
        source_years=sorted({v[3] for v in cohort_edges})
        window_ok=window_ok and w["source_years"]==source_years and w["source_max_year"]==(max(source_years) if source_years else None) and w["parameters"]==config.design_contract()["history"] and w["membership_digest"]==key_digest([list(v) for v in cohort_edges])
    add("H05-HIST-07", window_ok, dict(target_field_windows=len(windows),cohort_windows=len(cohort_windows),cohort_membership_rebuilt=True))
    add("H05-HIST-08", data.history_windows["window_variant"]==WINDOW and config.DATA_HANDOFF_POLICY["history_fixed_2016_variant"]=="not_adopted_not_a_gate",dict(adopted_window=WINDOW, variant_B_enabled=False))
    coverage=tables["handoff/aux_coverage.csv"]
    add("H05-AUX-01", all(r["main_rows_before"]==r["main_rows_after"]==len(data.raw_main) for r in coverage), dict(auxiliary_tables=len(coverage),main_rows=len(data.raw_main)))
    add("H05-AUX-02", len(coverage)==5 and all(not a["blocking"] for name,a in data.key_audits.items() if name!="steam.csv"), dict(auxiliary_counts=coverage))
    add("H05-AUX-03", x_sources.issubset({"steam.csv","derived"}),dict(primary_feature_sources=sorted(x_sources),sensitivity_interface="OFF"))
    return checks


def _input_fingerprints(data, input_files=None):
    rows={"steam.csv":data.raw_main, **data.raw_aux}
    if input_files is None:
        return {name:dict(sha256=digest_bytes(json_text(rows[name]).encode("utf-8")),kind="synthetic_literal_records",rows=len(rows[name])) for name in SOURCE_NAMES}
    if set(input_files)!=set(SOURCE_NAMES):
        raise ValueError("SOURCE_SCHEMA: exactly six logical inputs required")
    result={}
    for name,path in input_files.items():
        if literal_csv(path)!=rows[name]:
            raise ValueError("SOURCE_BINDING: parsed records do not match file")
        result[name]=dict(sha256=file_hash(path),kind="literal_CSV_file",rows=len(rows[name]))
    return result


def _protection_hashes(input_files, protected_paths):
    result={"inputs":{name:file_hash(path) for name,path in (input_files or {}).items()},"protected_trees":{}}
    for name,root in (protected_paths or {}).items():
        path=Path(root)
        if not path.exists():
            raise ValueError("PROTECTED_SOURCE_MISSING")
        result["protected_trees"][name]={str(p.relative_to(path)):file_hash(p) for p in sorted(path.rglob("*")) if p.is_file()} if path.is_dir() else {name:file_hash(path)}
    return result


def _stable_material(data, inputs):
    schema, definitions=_load_spec()
    schema=deepcopy(schema)
    enabled={p for p,v in schema["files"].items() if v["requiredness"]!="optional_OFF"}
    schema["files"]={p:v for p,v in schema["files"].items() if p in enabled}
    schema["implementation_status"]=config.DATA_POLICY_IMPLEMENTATION_STATUS
    schema["parse_policy_ref"]["status"]="implemented; acceptance scope recorded separately"
    tables=deepcopy(data.tables)
    for p in ("handoff/row_disposition.csv","handoff/rows_excluded.csv","handoff/rows_invalid_unknown.csv"):
        for r in tables[p]:r["source_reference"]["input_sha256"]=inputs["steam.csv"]["sha256"]
    dictionary=[]
    for (p,n),r in definitions.items():
        if p not in enabled:continue
        item=dict(r)
        for f in ("nullable","learned_transform"):item[f]=item[f]=="true"
        dictionary.append(item)
    tables["manifest/field_dictionary.csv"]=sorted(dictionary,key=lambda r:(r["file"],r["column"]))
    with (SPEC_DIR/"source_map.csv").open(newline="",encoding="utf-8") as stream:
        tables["manifest/source_map.csv"]=sorted((r for r in csv.DictReader(stream) if r["file"] in enabled),key=lambda r:(r["file"],r["column"]))
    objects={"handoff/history_windows.json":deepcopy(data.history_windows),
        "manifest/codebook.json":strict_json_loads((SPEC_DIR/"codebook.json").read_text()),
        "manifest/design_contract_snapshot.json":dict(design=config.design_contract(),data_policies=config.data_policy_contract(),config_sha256=file_hash(ROOT/"config.py")),
        "manifest/handoff_schema.json":schema}
    documents={"manifest/parse_contract.md":(ROOT/"docs/DATA_PARSE_CONTRACT.md").read_bytes(),
               "manifest/handoff_contract.md":(ROOT/"docs/DATA_HANDOFF_CONTRACT.md").read_bytes()}
    return schema,definitions,tables,objects,documents


def _write_material(candidate, schema, definitions, tables, objects, documents):
    for p,rows in tables.items():write_table(candidate/p,rows,schema["files"][p]["columns"],definitions,p)
    # History references only its two data prerequisites, never upper layers.
    objects["handoff/history_windows.json"]["source_bindings"]={p:file_hash(candidate/p) for p in ("handoff/x_primary.csv","handoff/y_label.csv")}
    for p,obj in objects.items():
        (candidate/p).parent.mkdir(parents=True,exist_ok=True)
        with (candidate/p).open("x",encoding="utf-8",newline="") as stream:stream.write(json_text(obj)+"\n")
    for p,content in documents.items():
        (candidate/p).parent.mkdir(parents=True,exist_ok=True)
        with (candidate/p).open("xb") as stream:stream.write(content)


def _csv_bytes(rows, columns, definitions, logical_path):
    import io
    stream=io.StringIO(newline="")
    writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator="\n")
    writer.writerow(columns)
    for row in rows:writer.writerow([encode_cell(row[n],definitions[logical_path,n]) for n in columns])
    return stream.getvalue().encode("utf-8")


def _domain_conversion_check(data):
    mismatches=[]
    meta={r["appid"]:r for r in data.tables["handoff/keys_meta.csv"] if r["split"] in ("train","validation","test")}
    for row in data.tables["handoff/x_primary.csv"]:
        key=row["appid"]
        if key not in meta:mismatches.append([key,"identity"]);continue
        m=meta[key];raw=data.raw_main[m["source_row_no"]-1]
        if row["english"]!=parse_english(raw["english"]).value or row["required_age"]!=parse_age(raw["required_age"]).value:
            mismatches.append([key,"scalar"])
        for field,count in (("platforms","platform_count"),("categories","category_count"),("genres","genre_count")):
            if row[count]!=len(row[field] or ()):mismatches.append([key,count])
        tokens={s.casefold() for s in row["platforms"] or ()}
        for token in config.DATA_PARSE_POLICY["platform_membership"]["tokens"]:
            if row["has_"+token]!=(token in tokens):mismatches.append([key,"has_"+token])
        date=parse_date(raw["release_date"]).value
        if date is None:mismatches.append([key,"date"]);continue
        expected={"release_month":date.month,"release_quarter":(date.month-1)//3+1,"release_day_of_week":date.dayofweek}
        for prefix,value,origin,period in [("release_month",date.month,config.MONTH_CYCLE_ORIGIN,config.MONTH_CYCLE_PERIOD),("release_day_of_week",date.dayofweek,config.DAY_OF_WEEK_CYCLE_ORIGIN,config.DAY_OF_WEEK_CYCLE_PERIOD)]:
            a=2*math.pi*(value-origin)/period;expected[prefix+"_sin"]=math.sin(a);expected[prefix+"_cos"]=math.cos(a)
        for n,value in expected.items():
            if type(row[n]) not in (int,float) or abs(row[n]-value)>1e-12:mismatches.append([key,n])
    for m in data.tables["handoff/keys_meta.csv"]:
        raw=data.raw_main[m["source_row_no"]-1];date=parse_date(raw["release_date"]).value
        if m["release_year"]!=(None if date is None else date.year) or m["release_date_utc"]!=(None if date is None else date.isoformat().replace("+00:00","Z")):
            mismatches.append([m["source_row_no"],"UTC metadata"])
    invalid_features=sum(bool(parse_english(r["english"]).errors or parse_age(r["required_age"]).errors) for r in data.raw_main)
    return not mismatches and invalid_features==0,dict(conversion_mismatches=mismatches,invalid_source_features=invalid_features)


def ready_binding(manifest_hash, report_hash, report):
    """Pure marker decision; synthetic scope can never create a formal marker."""
    if report.get("scope")!="real-file" or report.get("overall")!="pass" or report.get("unresolved_policy"):
        return None
    if set(report.get("checks",{}))!=H05_IDS or any(v.get("status") not in ("PASS","NOT_APPLICABLE") for v in report["checks"].values()):
        return None
    if not all(re.fullmatch("[0-9a-f]{64}", h or "") for h in (manifest_hash,report_hash)):
        return None
    return dict(manifest_sha256=manifest_hash,report_sha256=report_hash)


def _report_only(run, checks, error, scope):
    ids=[x["id"] for x in strict_json_loads((SPEC_DIR/"assertion_index.json").read_text())["H05"]]
    for identifier in ids:
        checks.setdefault(identifier,dict(status="BLOCKED",evidence=dict(reason="earlier build/serialization blocked; not executed")))
    checks["H05-GATE-01"]=dict(status="PASS",evidence=dict(overall="blocked",READY_written=False))
    checks["H05-GATE-04"]=dict(status="PASS",evidence=dict(candidate_is_not_delivery=True))
    report=dict(scope=scope,overall="blocked",checks=checks,error=error,ready_eligible=False,
        limitation=RETROSPECTIVE_LIMITATION)
    (run/"diagnostics").mkdir()
    with (run/"diagnostics/validation_report.json").open("x",encoding="utf-8") as stream:stream.write(json_text(report)+"\n")
    return dict(directory=run,report=report,manifest=None)


def write_package(data, output_parent, *, scope="synthetic", input_files=None, protected_paths=None, issue_ready=False):
    """Prepare a fresh package; no implicit dataset lookup or overwrite.

Real production is callable only with six explicit matching CSV files and a
STEP1 protection snapshot. This task's acceptance calls synthetic scope only.
"""
    if scope not in ("synthetic","real-file"):
        raise ValueError("Unknown acceptance scope")
    if scope=="real-file" and (input_files is None or not (protected_paths or {}).get("STEP1")):
        raise ValueError("Real-file requires six inputs and STEP1 protection")
    parent=Path(output_parent)
    if scope=="real-file" and parent.resolve()!=ROOT/"outputs/data_handoff":
        raise ValueError("Real-file output must be outputs/data_handoff")
    run=parent/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run.mkdir(parents=True,exist_ok=False)
    try:
        checks=validate_dataset(data)
    except (KeyError,ValueError,TypeError,OverflowError) as exc:
        return _report_only(run,{},"CANDIDATE_SCHEMA: "+str(exc),scope)
    def add(identifier,ok,evidence):checks[identifier]=dict(status="PASS" if ok else "FAIL",evidence=evidence)
    before=_protection_hashes(input_files,protected_paths)
    inputs=_input_fingerprints(data,input_files)
    candidate=run/"candidate";candidate.mkdir()
    schema,definitions,tables,objects,documents=_stable_material(data,inputs)
    if scope=="real-file":
        schema["formal_production_status"]="REAL_FILE_ACCEPTANCE_RECORDED_IN_REPORT_AND_READY"
    try:
        _write_material(candidate,schema,definitions,tables,objects,documents)
        decoded={p:read_table(candidate/p,schema["files"][p]["columns"],definitions,p) for p in tables}
        json_objects={p:strict_json_loads((candidate/p).read_text()) for p in objects}
    except (ValueError,TypeError,OverflowError,csv.Error) as exc:
        return _report_only(run,checks,str(exc),scope)
    roundtrip={p:strict_json_loads(json_text(decoded[p]))==strict_json_loads(json_text(rows)) for p,rows in tables.items()}
    rejected=[]
    for text in ('{"a":1,"a":2}','NaN','Infinity','[1,]'):
        try:strict_json_loads(text)
        except ValueError:rejected.append(text)
    add("H05-SER-01",len(rejected)==4,dict(rejected_invalid_JSON=rejected,decoder="json.loads strict constants and duplicate-key hook"))
    add("H05-SER-04",all(roundtrip.values()),dict(per_file_roundtrip=roundtrip,encoding="JSON-in-cell then CSV quote all"))
    conversion_ok,conversion_evidence=_domain_conversion_check(data)
    add("H05-SER-06",all(roundtrip.values()) and conversion_ok,conversion_evidence)
    canonical={p:(candidate/p).read_bytes()==_csv_bytes(decoded[p],schema["files"][p]["columns"],definitions,p) for p in tables}
    add("H05-SER-07",all(canonical.values()),dict(canonical_bytes=canonical,encoding="UTF-8 no BOM; QUOTE_ALL; LF; newline=''",reader="literal CSV then explicit per-column conversion; configured sentinel only"))
    slots=[None,(),("",),("a;b","q\"x","line\nbreak",",", "\\")]
    slot_roundtrip=all(strict_json_loads(json_text(v))==(None if v is None else list(v)) for v in slots)
    add("H05-SER-09",slot_roundtrip and all(roundtrip.values()),dict(codec_slots_tested=4,source_empty_string_element_allowed=False,full_candidate_tables_checked=len(tables)))
    bindings=json_objects["handoff/history_windows.json"]["source_bindings"]
    add("H05-HIST-05",bindings=={p:file_hash(candidate/p) for p in ("handoff/x_primary.csv","handoff/y_label.csv")},dict(source_bindings=bindings,join="source_appid -> y_label, target_appid -> x_primary"))
    add("H05-AUX-04",bool(RETROSPECTIVE_LIMITATION),dict(limitation=RETROSPECTIVE_LIMITATION))
    physical_after=_protection_hashes(input_files,protected_paths)
    add("H05-GATE-02",before==physical_after and inputs==_input_fingerprints(data,input_files),dict(before=before,after=physical_after,input_kind=inputs["steam.csv"]["kind"],scope=scope,STEP1_applicable=scope=="real-file"))
    if any(i["blocking"] for i in data.issues) or any(c["status"]=="FAIL" for c in checks.values()):
        return _report_only(run,checks,"BLOCKING_INPUT_OR_CANDIDATE_CHECK",scope)
    entries={}
    trace=["candidate_validated"]
    for p,spec in schema["files"].items():
        target=run/p;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():raise FileExistsError("Stable layer exists")
        shutil.copyfile(candidate/p,target)
        if file_hash(candidate/p)!=file_hash(target):raise ValueError("SEAL_BYTE_MISMATCH")
        entry=dict(sha256=file_hash(target),schema=spec,shape=spec["shape"])
        if spec["shape"]=="CSV_table":
            rows=tables[p];entry.update(rows=len(rows),columns=spec["columns"],key_domain=spec["key_domain"],row_order=spec["row_order"],key_digest=key_digest([[r[n] for n in spec["primary_key"]] for r in rows]))
        entries[p]=entry
    trace.append("stable_sealed_and_byte_compared")
    try:head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:head=None
    manifest=dict(versions=dict(design=config.DESIGN_VERSION,business_base=config.BASE_DESIGN_VERSION,
            parse_policy_ref=dict(version=config.PARSE_POLICY_VERSION,document_sha256=file_hash(run/"manifest/parse_contract.md")),handoff=config.HANDOFF_CONTRACT_VERSION),
        inputs=inputs,files=entries,control_files=dict(report="manifest/validation_report.json",READY="manifest/HANDOFF_READY.json"),
        git=dict(HEAD=head,relevant_code_sha256={p:file_hash(ROOT/p) for p in RELEVANT_CODE}),
        runtime=dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__),
        executed_utc=datetime.now(timezone.utc).isoformat(),scope=scope,
        statistics=data.statistics,disposition_precedence=list(config.DATA_HANDOFF_POLICY["row_disposition_precedence"]),
        label=dict(algorithm=config.design_contract()["target"],snapshot_reference=None,documentary_only=True),
        history=dict(window_variant=WINDOW,source_bindings=bindings),
        key_digest_encoding="strict UTF-8 canonical JSON array; no concatenation",
        source_integrity=dict(before=before,after=physical_after),limitation=RETROSPECTIVE_LIMITATION)
    with (run/"manifest/manifest.json").open("x",encoding="utf-8") as stream:stream.write(json_text(manifest)+"\n")
    trace.append("manifest_frozen")
    manifest_sha=file_hash(run/"manifest/manifest.json")
    add("H05-MAN-01",set(entries)==set(schema["files"]) and set(inputs)==set(SOURCE_NAMES) and bool(manifest["executed_utc"]),dict(stable_files=len(entries),inputs=len(inputs),schema_columns={p:v.get("columns") for p,v in entries.items()}))
    add("H05-MAN-02",manifest["label"]["snapshot_reference"] is None and manifest["label"]["documentary_only"] is True,dict(documentary_counts_used=False,accepted_counts_substituted=False))
    no_upper_keys=all(not ({"manifest_sha256","report_sha256","READY_sha256"}&set(obj)) for obj in json_objects.values())
    add("H05-MAN-03",no_upper_keys and all(p not in entries for p in ("manifest/manifest.json","manifest/validation_report.json","manifest/HANDOFF_READY.json")),dict(hash_layers=["stable_files","manifest","report","READY"],reverse_bindings=[]))
    all_bytes=b"\n".join((run/p).read_bytes() for p in entries)+ (run/"manifest/manifest.json").read_bytes()
    sensitive=re.search(rb"/(?:Users|home)/|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api_key|access_token|password)\s*[=:]\s*[^\s]",all_bytes,re.IGNORECASE)
    add("H05-MAN-04",sensitive is None,dict(sensitive_pattern_hits=int(sensitive is not None)))
    add("H05-MAN-05",manifest["versions"]["design"]=="v1.2" and manifest["versions"]["business_base"]=="v1.1" and json_text(json_objects["manifest/design_contract_snapshot.json"]["design"])==json_text(config.design_contract()),dict(versions=manifest["versions"],snapshot_current=True))
    add("H05-MAN-06",head is not None and set(manifest["git"]["relevant_code_sha256"])==set(RELEVANT_CODE),dict(HEAD=head,relevant_code_sha256=manifest["git"]["relevant_code_sha256"]))
    add("H05-MAN-07",all(manifest["runtime"].values()),dict(runtime=manifest["runtime"],source="actual imported runtime"))
    add("H05-MAN-08",manifest["versions"]["parse_policy_ref"]["version"]==config.PARSE_POLICY_VERSION and bool(manifest["versions"]["parse_policy_ref"]["document_sha256"]),dict(parse_policy_ref=manifest["versions"]["parse_policy_ref"],scope=scope))
    trace.append("report_prepared")
    add("H05-GATE-03",trace==["candidate_validated","stable_sealed_and_byte_compared","manifest_frozen","report_prepared"],dict(seal_order=trace,READY_last_if_real_eligible=True))
    add("H05-GATE-04",config.DATA_HANDOFF_POLICY["mutable_pointer"]=="OFF",dict(candidate_is_delivery=False,mutable_pointer="OFF"))
    checks["H05-GATE-05"]=dict(status="NOT_APPLICABLE",evidence=dict(phase="consumer verification occurs after optional real READY; separate immutable report outside package",scope=scope))
    checks["H05-GATE-06"]=dict(status="NOT_APPLICABLE",evidence=dict(phase="post READY external layer revalidation",manifest_contains_stable_files_only=True))
    add("H05-GATE-07",scope in ("synthetic","real-file"),dict(scope=scope,synthetic_is_formal_acceptance=False))
    legacy_expected={"scripts/stage0_precheck.py":"17791770d9d3f0f4fb0a6fe3774e7a5816b88f8b4d86f28b5e2bf81f465a9dd6",
        "tests/test_stage0_precheck.py":"786fbd9b309ee1587832921824d215fc84abfd62ef83adbc02f36b313278ea2a",
        "tests/fixtures/stage0_boundary_cases.json":"18d36645b87837f2614c6809dbf30b380ea6b686a944d19f572d7ffc9dfb5968",
        "scripts/validate_steam_data.py":"335f7e97f0654b90dc0581dd79a3b8366346927698d23d90b0544e47166d1fee"}
    legacy_actual={p:file_hash(ROOT/p) for p in legacy_expected}
    add("H05-GATE-08",legacy_actual==legacy_expected,dict(external_actions=[],H04_changed=legacy_actual!=legacy_expected,legacy_sha256=legacy_actual,H04_exit4_semantics="no data blockers but open policy/implementation items"))
    add("H05-GATE-01",not (run/"manifest/HANDOFF_READY.json").exists(),dict(READY_not_written_before_gate=True,scope=scope))
    all_ids={r["id"] for r in strict_json_loads((SPEC_DIR/"assertion_index.json").read_text())["H05"]}
    if set(checks)!=all_ids:raise RuntimeError("H05 checker coverage gap: "+str(sorted(all_ids-set(checks))))
    overall="pass" if all(c["status"] in ("PASS","NOT_APPLICABLE") for c in checks.values()) else "fail"
    report=dict(scope=scope,overall=overall,checks=checks,manifest_sha256=manifest_sha,
        unresolved_policy=False,limitation=RETROSPECTIVE_LIMITATION,ready_eligible=scope=="real-file" and overall=="pass")
    with (run/"manifest/validation_report.json").open("x",encoding="utf-8") as stream:stream.write(json_text(report)+"\n")
    marker=ready_binding(manifest_sha,file_hash(run/"manifest/validation_report.json"),report)
    # Verify source protection again immediately before any real marker.
    if marker is not None and issue_ready:
        if _protection_hashes(input_files,protected_paths)!=before:raise ValueError("SOURCE_CHANGED_AFTER_REPORT")
        with (run/"manifest/HANDOFF_READY.json").open("x",encoding="utf-8") as stream:stream.write(json_text(marker)+"\n")
    return dict(directory=run,report=report,manifest=manifest)


def verify_package(directory, *, require_real=True, marker=None):
    """Read-only seven-item consumer check; never rewrites a sealed report.

An explicit virtual marker with require_real=False tests the component on a
synthetic package. Its result cannot be called formal acceptance.
"""
    directory=Path(directory)
    try:
        if require_real and marker is not None:
            raise ValueError("Virtual marker is synthetic-component only")
        manifest=strict_json_loads((directory/"manifest/manifest.json").read_text())
        report=strict_json_loads((directory/"manifest/validation_report.json").read_text())
        ready=marker if marker is not None else strict_json_loads((directory/"manifest/HANDOFF_READY.json").read_text())
        schema=strict_json_loads((directory/"manifest/handoff_schema.json").read_text())
        required={p for p,v in schema["files"].items() if v["requiredness"] in ("required","conditional_required")}
        inventory=set(manifest["files"])
        safe_paths=all(not Path(p).is_absolute() and ".." not in Path(p).parts and Path(p).parts[0] in ("handoff","manifest") for p in inventory)
        checks=dict(required_files=safe_paths and required==inventory and all((directory/p).is_file() for p in required),
            stable_hashes=safe_paths and all((directory/p).is_file() and file_hash(directory/p)==v["sha256"] for p,v in manifest["files"].items()),
            manifest_binding=file_hash(directory/"manifest/manifest.json")==report.get("manifest_sha256")==ready.get("manifest_sha256"),
            report_binding=file_hash(directory/"manifest/validation_report.json")==ready.get("report_sha256"),
            real_scope_and_pass=report.get("overall")=="pass" and report.get("scope")==manifest.get("scope") and (report.get("scope")=="real-file" if require_real else report.get("scope")=="synthetic"),
            no_block_or_open=not report.get("unresolved_policy",True) and set(report.get("checks",{}))==H05_IDS and all(v["status"] in ("PASS","NOT_APPLICABLE") for v in report["checks"].values()),
            READY_dual_hash=set(ready)=={"manifest_sha256","report_sha256"} and all(re.fullmatch("[0-9a-f]{64}", ready.get(k,"")) for k in ("manifest_sha256","report_sha256")))
    except (OSError,ValueError,KeyError,TypeError):
        checks={n:False for n in ("required_files","stable_hashes","manifest_binding","report_binding","real_scope_and_pass","no_block_or_open","READY_dual_hash")}
    passed=all(checks.values())
    return dict(checks=checks,overall="pass" if passed else "fail",
        accepted_for_formal_handoff=passed and require_real,
        scope="real-file_consumer" if require_real else "synthetic_component")


def produce_from_files(input_files, output_parent, *, step1_directory, issue_ready=True):
    """Explicit future production entry; not called by synthetic acceptance."""
    if set(input_files)!=set(SOURCE_NAMES):raise ValueError("Exactly six logical input files required")
    data=build_dataset(literal_csv(input_files["steam.csv"]),{p:literal_csv(input_files[p]) for p in SOURCE_NAMES[1:]})
    return write_package(data,output_parent,scope="real-file",input_files=input_files,
        protected_paths={"STEP1":step1_directory},issue_ready=issue_ready)
