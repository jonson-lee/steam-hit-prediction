# 项目更新记录

标准见[config.py](config.py)和[会议决议](docs/DECISIONS.md)，详细更新见[CHANGELOG](CHANGELOG.md)。

## 2026-10-12 — 数据交接与项目规整

- 正式21文件原字节迁入`data/processed/steam_handoff_v12/`；独立验收证据集中到`data/processed/acceptance/`。
- 21张EDA表、5对PNG/SVG、报告与结论修正集中到`reports/eda/`；项目展示文字入口为[EDA摘要](docs/EDA_SUMMARY.md)。
- 迁移保留61份有效产物，删除641个过期或过程文件，约83MB，包括STEP1旧交付、协作实验/候选稿、重复candidate、旧运行输出和旧Notebook。保留必要测试与固定基线。
- 新[建模指南](docs/MODELING_HANDOFF.md)与读入入口先验证READY/hash，再按appid返回24列X及独立标签、元数据和状态；不进行fit。
- R4仅显式更新3项文档绑定，保留R3 prior_binding。旧H04 11/11、当前150/150、新读入测试11/11均通过；整理后EDA21/21通过，21表和5PNG与原版字节一致。
- 完整微信ZIP经过CRC、逐文件SHA和独立解压读入验证。GitHub发布代码/测试/标准/摘要，数据、图表、验收原始记录与ZIP保持私下交接。
- 建模、训练、调参和模型评估尚未启动，2018已描述性查看的事实在指南中披露。

## 历史标准

- 2026-09-12：六表验收及条件通过，冻结热度标签、时间切分和特征边界。
- 2026-09-24：会议形成业务v1.1；2026-10-09完成采用与当前规则复算。
- 2026-10-11：采用数据政策v1.2，完成真实正式数据、READY、消费者核验及描述性EDA。
