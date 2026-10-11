# 文件与交接清单

当前项目分为实现、标准、正式数据、展示材料和可发送交接包。微信只需发送`deliverables/Steam_Modeling_Handoff_v1.2_2026-10-12.zip`一个文件；接收方解压后从[建模交接指南](MODELING_HANDOFF.md)开始。

| 目录/文件 | 用途 | GitHub | 微信ZIP |
|---|---|---|---|
| `config.py`、`src/`、`requirements.txt` | 同一业务政策及消费实现 | 保留 | 包含 |
| `scripts/`、`tests/` | 读入、复现、打包及固定验收 | 保留 | 包含 |
| `docs/`（内部日记/待办除外） | 接续说明、合同、字典及验收摘要 | 保留 | 包含 |
| `data/processed/steam_handoff_v12/` | 18稳定文件+3控制文件；完整正式包 | 不上传 | 包含全部21文件 |
| `data/processed/acceptance/` | 独立消费者与最终实测证据 | 不上传 | 包含交接所需最终证据；清理审计留本地 |
| `reports/eda/` | 报告、修正、21表、5对PNG/SVG | 仅文字摘要在`docs/EDA_SUMMARY.md` | 包含 |
| 项目提案、README、CHANGELOG、根JOURNAL | 商业问题、入口、团队更新 | 保留 | 包含 |
| `deliverables/` | ZIP及发送说明 | ZIP不上传 | 无须另发内部文件 |
| `data/raw/` | 原始输入位置说明；六CSV保留课程共享目录 | 只上传说明 | 只含说明，不含原CSV |
| `outputs/`、`.venv/`、内部日记/待办 | 临时复现结果、环境及本地管理 | 不上传 | 不包含 |

主数据从`handoff/x_primary.csv`、`y_label.csv`、`keys_meta.csv`及`x_entity_states.csv`读入，其余文件用于READY校验、字典、历史来源和完整性审计。不能只发两张CSV，拆包会丢掉读入所需的schema和验收绑定。

清除范围包括旧STEP1、协作实验、派发/回传/候选稿、历史预检/失败运行、重复candidate、旧Notebook和根目录重复决议。必要旧H04 fixtures作为当前验收的一部分保留；R3旧hash作为R4的prior_binding保留。六原输入、正式21文件及原21展示数值表没有改变。

详细删除清单保存在本地`data/processed/acceptance/cleanup_20261012.json`。当前项目仍未训练或评估模型。
