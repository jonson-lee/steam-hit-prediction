"""按当前版本化设计运行 Steam 数据审计，每次写入独立目录。

运行：python -m src.data_audit_reproduce
标准：config.py 与 docs/DECISIONS.md 中的会议决议。
"""

import json

from config import DESIGN_VERSION
from scripts.validate_steam_data import audit

from .project_paths import create_run_dir, find_steam_csv


def main():
    data_dir = find_steam_csv().parent
    result = audit(data_dir)
    output_dir = create_run_dir("data_audit")
    output_file = output_dir / "steam_data_audit.json"
    output_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Design: {DESIGN_VERSION}")
    print(f"Input: {data_dir}")
    print(f"Output: {output_file}")
    print(f"File integrity: {result['verdict']['file_integrity']}")
    print(f"Analytical acceptance: {result['verdict']['analytical_acceptance']}")
    for year, metrics in result["time_safe_rule_baseline"].items():
        print(
            f"{year}: ROC-AUC={metrics['roc_auc']:.6f}, "
            f"AP={metrics['average_precision']:.6f}, "
            f"Lift@10%={metrics['top_10_percent']['expected_lift']:.6f}"
        )


if __name__ == "__main__":
    main()
