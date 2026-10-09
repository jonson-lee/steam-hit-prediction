"""统一项目路径；原始输入只读，新运行写入独立目录。"""

from datetime import datetime, timezone
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def find_steam_csv():
    """优先显式输入，其次项目原始数据，最后课程共享数据。"""
    configured_path = os.environ.get("STEAM_DATA_PATH")
    if configured_path:
        path = Path(configured_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"STEAM_DATA_PATH 指定的文件不存在：{path}")
        return path

    candidates = (
        RAW_DATA_DIR / "steam.csv",
        RAW_DATA_DIR / "steam_store_games" / "steam.csv",
        PROJECT_ROOT.parent / "06_Datasets" / "steam" / "steam.csv",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "找不到 steam.csv。请放入项目 data/raw/，"
        "或设置 STEAM_DATA_PATH 为数据文件路径。"
    )


def create_run_dir(stage):
    """为每次运行创建独立的 UTC 时间戳目录，不覆盖历史结果。"""
    if not stage or Path(stage).name != stage or stage in {".", ".."}:
        raise ValueError("stage 必须是单个目录名称")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    path = OUTPUTS_DIR / stage / timestamp
    path.mkdir(parents=True, exist_ok=False)
    return path
