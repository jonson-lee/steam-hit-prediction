# 原始数据

当前验证需要同一目录中的六张 CSV：`steam.csv`、`steam_description_data.csv`、`steam_media_data.csv`、`steam_requirements_data.csv`、`steam_support_info.csv`、`steamspy_tag_data.csv`。原始输入只读，不进入 Git。

主表定位顺序：`STEAM_DATA_PATH` 环境变量 → `data/raw/steam.csv` → `data/raw/steam_store_games/steam.csv` → 课程共享 `../06_Datasets/steam/steam.csv`。入口读取主表所在目录的六张 CSV；无需复制现有课程数据。

运行：`python -m src.data_audit_reproduce`。来源与许可见 [数据说明](../README.md)，标准见 [会议决议](../../docs/DECISIONS.md) 与 [config.py](../../config.py)。
