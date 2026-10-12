"""Read the sealed Steam handoff into aligned, untransformed model inputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from src import steam_handoff as handoff
from src.steam_parse import parse_appid

DEFAULT_PACKAGE = ROOT / "data/processed/steam_handoff_v12"
SPLITS = ("train", "validation", "test")


def _json_value(value):
    """Compare JSON snapshots without mistaking tuple/list wire conversion for drift."""
    return handoff.strict_json_loads(handoff.json_text(value))


def _keyed(frame, name):
    keys = frame["appid"]
    if any(not isinstance(key, str) or parse_appid(key).value != key for key in keys):
        raise ValueError(f"Invalid string appid in {name}")
    if keys.duplicated().any():
        raise ValueError(f"Duplicate appid in {name}")
    return frame.set_index("appid")


def load_modeling_data(package_dir=None):
    """Return split -> {X, y, metadata, states}, with string appid indexes.

    X contains exactly the 24 configured predictors; y contains only hit_reviews.
    Sequence cells are Python lists or None, preserving JSON [] versus null.
    No imputation, vocabulary fitting, scaling, encoding or training occurs here.
    The package may be relocated; its sealed bytes and current config must match.
    """
    package = Path(package_dir).expanduser().resolve() if package_dir is not None else DEFAULT_PACKAGE
    verification = handoff.verify_package(package, require_real=True)
    if (verification.get("overall") != "pass"
            or not verification.get("accepted_for_formal_handoff")):
        failed = [name for name, passed in verification.get("checks", {}).items() if not passed]
        raise ValueError("Formal handoff verification failed: " + ", ".join(failed))

    def read_json(name):
        return handoff.strict_json_loads((package / "manifest" / name).read_text(encoding="utf-8"))

    snapshot = read_json("design_contract_snapshot.json")
    if (snapshot.get("config_sha256") != handoff.file_hash(ROOT / "config.py")
            or snapshot.get("design") != _json_value(config.design_contract())
            or snapshot.get("data_policies") != _json_value(config.data_policy_contract())):
        raise ValueError("Sealed configuration snapshot does not match current config.py")

    schema = read_json("handoff_schema.json")
    manifest = read_json("manifest.json")
    versions = manifest.get("versions", {})
    if (versions.get("design") != config.DESIGN_VERSION
            or versions.get("business_base") != config.BASE_DESIGN_VERSION
            or versions.get("handoff") != config.HANDOFF_CONTRACT_VERSION
            or versions.get("parse_policy_ref", {}).get("version") != config.PARSE_POLICY_VERSION):
        raise ValueError("Sealed package versions do not match current config.py")

    expected_x = ["appid", *config.PRIMARY_FEATURE_COLUMNS]
    if schema["files"]["handoff/x_primary.csv"]["columns"] != expected_x:
        raise ValueError("Primary feature schema must be appid plus the exact 24-column whitelist")
    config.assert_primary_feature_columns(expected_x[1:])

    definitions = {}
    with (package / "manifest/field_dictionary.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["file"], row["column"])
            if key in definitions:
                raise ValueError("Duplicate field dictionary definition: " + str(key))
            definitions[key] = row
    if any(definitions["handoff/x_primary.csv", name]["role"] != "primary_x"
           for name in config.PRIMARY_FEATURE_COLUMNS):
        raise ValueError("Primary feature dictionary roles do not match the whitelist")

    def load(name):
        logical = f"handoff/{name}.csv"
        columns = schema["files"][logical]["columns"]
        records = handoff.read_table(package / logical, columns, definitions, logical)
        # Object construction keeps nullable Int64 values exact before schema casts.
        frame = pd.DataFrame(records, columns=columns, dtype=object)
        for column in columns:
            spec = definitions[logical, column]
            storage = spec["storage_type"]
            if spec["logical_type"] == "nullable_ordered_string_sequence":
                frame[column] = frame[column].map(lambda value: None if value is None else list(value))
            elif storage.startswith("Int"):
                frame[column] = frame[column].astype(storage)
            elif storage == "boolean_text":
                frame[column] = frame[column].astype("boolean")
            elif storage == "float64":
                frame[column] = frame[column].astype("float64")
            elif storage != "JSON-in-cell":
                frame[column] = frame[column].astype("string")
        return frame

    x, y, metadata, states = [load(name) for name in
                              ("x_primary", "y_label", "keys_meta", "x_entity_states")]
    if metadata.duplicated(["source_file", "source_row_no"]).any():
        raise ValueError("Duplicate source identity in keys_meta")
    statistics = manifest["statistics"]
    if len(metadata) != statistics["source_records"]:
        raise ValueError("Metadata source row count differs from manifest")
    metadata = metadata.loc[metadata["split"].isin(SPLITS)].copy()
    keyed = {name: _keyed(frame, name) for name, frame in
             (("X", x), ("y", y), ("metadata", metadata), ("states", states))}
    keys = keyed["X"].index.sort_values()
    if any(set(frame.index) != set(keys) for frame in keyed.values()):
        raise ValueError("X/y/metadata/states appid key domains differ")
    keyed = {name: frame.loc[keys].copy() for name, frame in keyed.items()}
    x, y, metadata, states = [keyed[name] for name in ("X", "y", "metadata", "states")]
    if len(x) != statistics["developed_rows"]:
        raise ValueError("Developed row count differs from manifest")
    target = config.TARGET_COLUMN
    if y[target].isna().any() or not y[target].isin((0, 1)).all():
        raise ValueError("Target must contain nonmissing binary hit_reviews")
    if int(y[target].sum()) != statistics["developed_positive_sum"]:
        raise ValueError("Developed positive count differs from manifest")

    years = metadata["release_year"]
    expected_split = pd.Series(pd.NA, index=keys, dtype="string")
    expected_split.loc[years.le(config.TRAIN_MAX_YEAR).fillna(False)] = "train"
    expected_split.loc[years.eq(config.VALIDATION_YEAR).fillna(False)] = "validation"
    expected_split.loc[years.eq(config.TEST_YEAR).fillna(False)] = "test"
    if (expected_split.isna().any() or years.isin(config.EXCLUDED_RELEASE_YEARS).any()
            or not expected_split.equals(metadata["split"])):
        raise ValueError("Metadata violates the configured release-year split")
    for field in config.DATA_PARSE_POLICY["sequences"]["fields"]:
        expected_states = x[field].map(lambda value: "S_MISSING" if value is None else
                                       "S_EMPTY_LIST" if not value else "S_LIST")
        if not expected_states.eq(states[field]).all():
            raise ValueError("Sequence state does not match decoded X: " + field)

    result = {}
    for split in SPLITS:
        selected = metadata["split"].eq(split)
        if int(selected.sum()) != statistics["dispositions"].get(split, 0):
            raise ValueError("Split row count differs from manifest: " + split)
        result[split] = {
            "X": x.loc[selected, list(config.PRIMARY_FEATURE_COLUMNS)].copy(),
            "y": y.loc[selected, [target]].copy(),
            "metadata": metadata.loc[selected].copy(),
            "states": states.loc[selected].copy(),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, help="Default: data/processed/steam_handoff_v12")
    args = parser.parse_args()
    data = load_modeling_data(args.package_dir)
    print(json.dumps({"formal_package_verified": True, "modeling_started": False,
                      "splits": {split: {"rows": len(part["X"]), "features": part["X"].shape[1],
                                          "positives": int(part["y"][config.TARGET_COLUMN].sum())}
                                 for split, part in data.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
