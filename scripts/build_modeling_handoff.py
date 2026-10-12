"""Build a complete private modeling ZIP without raw inputs or process files."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.load_modeling_data import load_modeling_data
from src.steam_handoff import file_hash, strict_json_loads

ROOT_FILES = (
    ".gitignore", "AGENTS.md", "README.md", "CHANGELOG.md", "JOURNAL.md",
    "Project_Proposal_Steam_Game_Success.md", "config.py", "requirements.txt",
    "data/README.md", "data/raw/README.md", "data/processed/README.md",
    "data/processed/Steam_数据交接中英文对照表.xlsx",
)
EVIDENCE_FILES = (
    "consumer_acceptance_20261011.json", "official_consumer_20261011.json",
    "independent_audit_20261011.json", "contract_acceptance_R3_20261011.json",
    "contract_acceptance_R4_20261012.json", "eda_validation_20261011.json",
    "eda_independent_review_20261011.json", "eda_validation_relocated_20261012.json",
    "modeling_loader_20261012.json",
    "contract_acceptance_R5_20261012.json", "reader_boundary_fix_20261012.json",
    "contract_acceptance_R6_20261012.json", "handoff_fix_20261012.json",
    "contract_acceptance_R7_20261012.json", "source_identity_fix_20261012.json",
)


def delivery_files():
    """Use explicit allowlists; local environments and ignored files never leak in."""
    files = {ROOT / name for name in ROOT_FILES}
    for directory, suffixes in (
        ("src", {".py"}), ("scripts", {".py"}), ("tests", {".py", ".json"}),
        ("docs", {".md", ".json", ".csv"}),
        ("reports/eda", {".md", ".json", ".csv", ".png", ".svg"}),
    ):
        files.update(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and path.suffix in suffixes
                     and "__pycache__" not in path.parts)
    files.difference_update({ROOT / "docs/NEXT.md", ROOT / "docs/JOURNAL.md"})
    package = ROOT / "data/processed/steam_handoff_v12"
    manifest = strict_json_loads((package / "manifest/manifest.json").read_text(encoding="utf-8"))
    formal = set(manifest["files"]) | {"manifest/manifest.json", *manifest["control_files"].values()}
    if len(formal) != 21 or any(Path(name).is_absolute() or ".." in Path(name).parts for name in formal):
        raise ValueError("Expected the complete sealed 21-file handoff")
    files.update(package / name for name in formal)
    files.update(ROOT / "data/processed/acceptance" / name for name in EVIDENCE_FILES)
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Required regular delivery file missing: {path.relative_to(ROOT)}")
    return sorted(files)


def build(output=None):
    date = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    name = f"Steam_Modeling_Handoff_v1.2_{date}"
    target = Path(output).expanduser().resolve() if output else ROOT / "deliverables" / (name + ".zip")
    if target.suffix.lower() != ".zip":
        raise ValueError("Output must be a new .zip file")
    if target.exists():
        raise FileExistsError("Delivery already exists; use --output with a new filename")
    data = load_modeling_data()
    paths = delivery_files()
    hashes = {path.relative_to(ROOT).as_posix(): file_hash(path) for path in paths}
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            archive.write(path, name + "/" + path.relative_to(ROOT).as_posix())
        archive.writestr(name + "/SHA256SUMS.json",
                         json.dumps(hashes, ensure_ascii=False, indent=2) + "\n")
        archive.writestr(name + "/DELIVERY.json", json.dumps({
            "delivery_date": date, "timezone": "Asia/Shanghai",
            "policy": "v1.2", "business_base": "v1.1", "formal_package_files": 21,
            "payload_files": len(paths), "raw_inputs_included": False,
            "model_training_performed": False,
            "splits": {split: {"rows": len(part["X"]), "features": part["X"].shape[1],
                               "positives": int(part["y"]["hit_reviews"].sum())}
                       for split, part in data.items()},
        }, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC verification failed")
        for relative, expected in hashes.items():
            if hashlib.sha256(archive.read(name + "/" + relative)).hexdigest() != expected:
                raise ValueError("ZIP file hash differs: " + relative)
    if hashes != {path.relative_to(ROOT).as_posix(): file_hash(path) for path in paths}:
        raise ValueError("Source delivery changed while packaging")
    return {"zip": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
            "bytes": target.stat().st_size, "files": len(paths) + 2,
            "sha256": file_hash(target), "formal_package_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New ZIP path; existing files are never overwritten")
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
