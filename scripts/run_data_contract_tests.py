"""Run frozen H04 and current B05 implementation acceptance on synthetic data.

The historical module runs unchanged in an isolated v1.1 copy.  The current
modules run in a separate process and publish assertion evidence only after
unittest has actually executed them.  Neither process receives raw data paths.
An unbound or changed v1.2 baseline fails closed; this runner never rebaselines.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


sys.dont_write_bytecode = True
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "tests/fixtures/v12_baseline.json"
ASSERTION_INDEX_PATH = PROJECT_ROOT / "docs/data_contract/assertion_index.json"
LEGACY_SHA256 = {
    "scripts/stage0_precheck.py":
        "17791770d9d3f0f4fb0a6fe3774e7a5816b88f8b4d86f28b5e2bf81f465a9dd6",
    "tests/fixtures/stage0_boundary_cases.json":
        "18d36645b87837f2614c6809dbf30b380ea6b686a944d19f572d7ffc9dfb5968",
    "tests/test_stage0_precheck.py":
        "786fbd9b309ee1587832921824d215fc84abfd62ef83adbc02f36b313278ea2a",
    "tests/fixtures/legacy_v11/config.py":
        "63991ed1e5033d0f5e885f4747c6b95339e0fbeb4f53cefb878ab11571eeb91e",
}
CURRENT_REQUIRED_PATHS = frozenset({
    "config.py", "src/steam_parse.py", "src/steam_handoff.py",
    "scripts/run_data_contract_tests.py", "tests/test_design_contract.py",
    "tests/v12/test_parse.py", "tests/v12/test_handoff.py",
    "docs/DATA_PARSE_CONTRACT.md", "docs/DATA_HANDOFF_CONTRACT.md",
    "docs/data_contract/handoff_schema.json", "docs/data_contract/field_dictionary.csv",
    "docs/data_contract/source_map.csv", "docs/data_contract/codebook.json",
    "docs/data_contract/policy_snapshot.json", "docs/data_contract/assertion_index.json",
})


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    """Only new files are allowed, including evidence and worker reports."""
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def read_json(path):
    def reject_constant(token):
        raise ValueError("non-finite JSON constant: " + token)
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=reject_constant)


def subprocess_environment():
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTHONPATH", None)
    environment.pop("STEAM_DATA_PATH", None)
    return environment


def run_process(argv, cwd, output_dir, stem):
    started = time.monotonic()
    result = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, check=False,
        env=subprocess_environment(),
    )
    for stream in ("stdout", "stderr"):
        with (output_dir / (stem + "." + stream + ".txt")).open(
                "x", encoding="utf-8", newline="\n") as handle:
            handle.write(getattr(result, stream))
    evidence = {
        "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 6),
        "stdout": stem + ".stdout.txt",
        "stderr": stem + ".stderr.txt",
    }
    write_json(output_dir / (stem + ".process.json"), evidence)
    return evidence


def check_legacy_bindings():
    return [
        {"path": relative, "expected_sha256": expected,
         "actual_sha256": sha256(PROJECT_ROOT / relative)
         if (PROJECT_ROOT / relative).is_file() else None,
         "status": "PASS" if (PROJECT_ROOT / relative).is_file()
         and sha256(PROJECT_ROOT / relative) == expected else "FAIL"}
        for relative, expected in LEGACY_SHA256.items()
    ]


def run_legacy(output_dir):
    """Execute all eleven old tests with the old guard and exact config bytes."""
    before = check_legacy_bindings()
    if any(item["status"] != "PASS" for item in before):
        return {"status": "FAIL", "scope": "synthetic_legacy_v1.1",
                "reason": "frozen legacy files differ", "bindings": before,
                "tests_expected": 11, "tests_executed": 0}
    with tempfile.TemporaryDirectory(prefix="steam-h04-v11-") as directory:
        isolated = Path(directory)
        copied = {
            "scripts/stage0_precheck.py": "scripts/stage0_precheck.py",
            "tests/fixtures/stage0_boundary_cases.json":
                "tests/fixtures/stage0_boundary_cases.json",
            "tests/test_stage0_precheck.py": "tests/test_stage0_precheck.py",
            "tests/fixtures/legacy_v11/config.py": "config.py",
        }
        for source, destination in copied.items():
            path = isolated / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / source, path)
            if sha256(path) != LEGACY_SHA256[source]:
                raise AssertionError("legacy copy did not preserve " + source)
        argv = [sys.executable, "-B", "-m", "unittest", "discover",
                "-s", "tests", "-p", "test_stage0_precheck.py", "-v"]
        process = run_process(argv, isolated, output_dir, "legacy_h04")
    after = check_legacy_bindings()
    # The unchanged runner has eleven test methods.  Check the real result text
    # as well as the exit code, so a discovery error cannot become a PASS.
    stderr = (output_dir / "legacy_h04.stderr.txt").read_text(encoding="utf-8")
    ran_eleven = "Ran 11 tests in " in stderr
    passed = process["exit_code"] == 0 and ran_eleven and before == after
    return {
        "status": "PASS" if passed else "FAIL",
        "scope": "synthetic_legacy_v1.1",
        "business_version": "v1.1", "tests_expected": 11,
        "tests_executed": 11 if ran_eleven else None,
        "original_files_unchanged": before == after,
        "bindings": before, "process": process,
        "note": "Unchanged H04 guard executes against frozen v1.1 bytes; "
                "this is not current v1.2 coverage.",
    }


def expected_assertions():
    index = read_json(ASSERTION_INDEX_PATH)
    result = {}
    for prefix, count in (("P05", 53), ("H05", 68)):
        entries = index.get(prefix)
        if not isinstance(entries, list):
            raise ValueError(prefix + " assertion definitions are absent")
        ids = [item["id"] for item in entries]
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError(prefix + " definitions are incomplete or duplicated")
        if any(not item.startswith(prefix + "-") for item in ids):
            raise ValueError(prefix + " definition has an invalid ID")
        result[prefix] = ids
    return result


def check_current_baseline():
    baseline = read_json(BASELINE_PATH)
    problems = []
    required_versions = {
        "design_version": "v1.2", "business_base": "v1.1",
        "parse_policy": "steam-parse/v1", "handoff_contract": "steam-handoff/v1",
    }
    if baseline.get("versions") != required_versions:
        problems.append("v1.2 version metadata differs")
    if baseline.get("legacy_sha256") != LEGACY_SHA256:
        problems.append("historical binding metadata differs")
    if baseline.get("expected_assertion_counts") != {"P05": 53, "H05": 68}:
        problems.append("assertion target counts differ")
    bindings = baseline.get("implementation_sha256")
    checks = []
    if not isinstance(bindings, dict) or not bindings:
        problems.append("implementation bindings are absent")
        bindings = {}
    required_paths = set(CURRENT_REQUIRED_PATHS)
    test_paths = sorted(PROJECT_ROOT.glob("tests/v12/test_*.py"))
    if not test_paths:
        problems.append("no v1.2 test modules exist")
    required_paths.update(str(path.relative_to(PROJECT_ROOT)) for path in test_paths)
    missing_bindings = sorted(required_paths - set(bindings))
    if missing_bindings:
        problems.append("unbound required files: " + ", ".join(missing_bindings))
    unexpected_bindings = sorted(set(bindings) - required_paths)
    if unexpected_bindings:
        problems.append("binding outside task scope: " + ", ".join(unexpected_bindings))
    for relative, expected in sorted(bindings.items()):
        path = PROJECT_ROOT / relative
        safe_path = not Path(relative).is_absolute() and ".." not in Path(relative).parts
        actual = sha256(path) if safe_path and path.is_file() else None
        valid_hash = (isinstance(expected, str) and len(expected) == 64
                      and all(char in "0123456789abcdef" for char in expected))
        passed = valid_hash and actual == expected
        checks.append({"path": relative, "expected_sha256": expected,
                       "actual_sha256": actual, "status": "PASS" if passed else "FAIL"})
        if not passed:
            problems.append("unbound or changed implementation file: " + relative)
    return baseline, checks, problems


def load_test_module(path, index):
    name = "data_contract_acceptance_test_" + str(index)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load test module " + path.name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def collect_assertions(modules, expected):
    collected = {"P05": {}, "H05": {}}
    problems = []
    for module in modules:
        for prefix in collected:
            values = getattr(module, prefix + "_RESULTS", {})
            if not isinstance(values, dict):
                problems.append(module.__name__ + ": invalid " + prefix + "_RESULTS")
                continue
            for assertion_id, result in values.items():
                if assertion_id in collected[prefix]:
                    problems.append("duplicate executed assertion: " + assertion_id)
                    continue
                if not isinstance(result, dict) or result.get("status") != "PASS":
                    problems.append("assertion failed or lacks real result: " + assertion_id)
                elif result.get("evidence") in (None, "", [], {}):
                    problems.append("assertion has no evidence: " + assertion_id)
                collected[prefix][assertion_id] = result
    for prefix in collected:
        missing = sorted(set(expected[prefix]) - set(collected[prefix]))
        extra = sorted(set(collected[prefix]) - set(expected[prefix]))
        if missing:
            problems.append("missing executed " + prefix + " assertions: " + ", ".join(missing))
        if extra:
            problems.append("unknown executed " + prefix + " assertions: " + ", ".join(extra))
    return collected, problems


def run_current_worker(result_path):
    """Private subprocess entry: collect globals only after actual unittest."""
    sys.path.insert(0, str(PROJECT_ROOT))
    baseline, _, baseline_problems = check_current_baseline()
    if baseline_problems:
        write_json(result_path, {"status": "FAIL", "scope": "synthetic",
                                 "tests_run": 0, "problems": baseline_problems})
        return 1
    import config
    versions = {
        "design_version": config.DESIGN_VERSION,
        "business_base": config.BASE_DESIGN_VERSION,
        "parse_policy": config.PARSE_POLICY_VERSION,
        "handoff_contract": config.HANDOFF_CONTRACT_VERSION,
    }
    if versions != baseline["versions"]:
        write_json(result_path, {"status": "FAIL", "scope": "synthetic",
                                 "tests_run": 0, "versions": versions,
                                 "problems": ["actual config versions differ from baseline"]})
        return 1
    expected = expected_assertions()
    paths = [PROJECT_ROOT / "tests/test_design_contract.py"]
    paths.extend(sorted(PROJECT_ROOT.glob("tests/v12/test_*.py")))
    if len(paths) < 2:
        raise ValueError("v1.2 test modules are missing")
    modules = [load_test_module(path, index) for index, path in enumerate(paths)]
    suite = unittest.TestSuite()
    for module in modules:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    collected, problems = collect_assertions(modules, expected)
    if result.testsRun == 0:
        problems.append("unittest executed zero cases")
    if result.skipped:
        problems.append("unittest skipped cases; acceptance is incomplete")
    passed = result.wasSuccessful() and not problems
    report = {
        "status": "PASS" if passed else "FAIL", "scope": "synthetic",
        "versions": versions,
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "test_modules": [str(path.relative_to(PROJECT_ROOT)) for path in paths],
        "assertion_results": collected,
        "executed_assertion_counts": {key: len(value) for key, value in collected.items()},
        "expected_assertion_counts": {key: len(value) for key, value in expected.items()},
        "problems": problems,
    }
    write_json(result_path, report)
    return 0 if passed else 1


def run_acceptance(legacy_only=False):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output_dir = PROJECT_ROOT / "outputs/data_contract_implementation" / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "steam-data-contract-implementation-acceptance/v1",
        "scope": "synthetic", "created_utc": datetime.now(timezone.utc).isoformat(),
        "formal_data_created": False, "modeling_started": False,
        "handoff_ready_created": False, "automatic_rebaseline": False,
        "legacy_h04": run_legacy(output_dir),
    }
    if legacy_only:
        report["mode"] = "legacy_only"
        report["current_v1.2"] = {"status": "NOT_RUN"}
        passed = report["legacy_h04"]["status"] == "PASS"
    else:
        baseline, bindings, problems = check_current_baseline()
        report["v1.2_baseline"] = {
            "path": str(BASELINE_PATH.relative_to(PROJECT_ROOT)),
            "sha256": sha256(BASELINE_PATH), "versions": baseline.get("versions"),
            "bindings": bindings, "problems": problems,
        }
        if problems:
            report["current_v1.2"] = {
                "status": "FAIL", "tests_run": 0,
                "reason": "v1.2 baseline gate rejected execution",
            }
        else:
            worker_path = output_dir / "current_worker.json"
            process = run_process(
                [sys.executable, "-B", "-m", "scripts.run_data_contract_tests",
                 "--worker", str(worker_path)], PROJECT_ROOT, output_dir, "current_v12",
            )
            if worker_path.is_file():
                current = read_json(worker_path)
            else:
                current = {"status": "FAIL", "reason": "worker produced no evidence"}
            current["process"] = process
            if process["exit_code"] != 0:
                current["status"] = "FAIL"
            after_baseline, after_bindings, after_problems = check_current_baseline()
            unchanged = after_baseline == baseline and after_bindings == bindings
            current["bound_files_unchanged_after_execution"] = unchanged
            if not unchanged or after_problems:
                current["status"] = "FAIL"
                current["post_execution_problems"] = after_problems
            report["current_v1.2"] = current
        passed = (report["legacy_h04"]["status"] == "PASS"
                  and report["current_v1.2"]["status"] == "PASS")
    report["overall"] = "PASS" if passed else "FAIL"
    write_json(output_dir / "acceptance.json", report)
    print(json.dumps({"overall": report["overall"], "scope": "synthetic",
                      "output": str(output_dir.relative_to(PROJECT_ROOT))},
                     ensure_ascii=False, allow_nan=False))
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-only", action="store_true",
                        help="Verify only the frozen historical eleven tests.")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.worker is not None:
        if arguments.legacy_only:
            parser.error("--worker and --legacy-only are mutually exclusive")
        return run_current_worker(arguments.worker)
    return run_acceptance(legacy_only=arguments.legacy_only)


if __name__ == "__main__":
    raise SystemExit(main())
