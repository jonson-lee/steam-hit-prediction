# Steam 项目工作约定

修改前阅读`README.md`、`config.py`、`docs/PROJECT_CONTEXT.md`、`docs/DECISIONS.md`、`docs/NEXT.md`和`docs/MODELING_HANDOFF.md`。

- 数据阶段及2026-10-12交接整理已完成；建模交给组员，本代理不自行训练、调参或评估模型。
- `config.py`是唯一机器政策源：政策v1.2、业务v1.1。改变业务规则须先升版本并记录决议；不在Notebook或脚本另定口径。
- 标签为同发行年评论总量linear q90、inclusive `>=`，小cohort保留，2019全部排除；train≤2016、validation2017、test2018。
- 历史按`;`多实体、严格较早发行年、游戏并集去重；alpha10/prior0.10/log1p。窗口A中2018可含2017，模型/规则比较须统一窗口。
- SteamSpy tags/tag_count、ratings、owners、playtime和标签派生字段禁止进X；快照price/achievements/辅助表仅作敏感性。ID/态/split/标签/审计元数据剔除后才是24列主X。
- 正式包固定在`data/processed/steam_handoff_v12/`，21文件原字节只读，物理READY与消费者验收已通过；不覆盖、不回写报告。封存合同及config阶段字段是历史快照，当前完成状态看验收摘要。
- 原始六表在课程共享目录只读；STEP1旧交付、candidate重复副本和协作过程已按用户2026-10-12授权删除。删除清单与最终验收证据在本地`data/processed/acceptance/`。
- `python -B -m scripts.load_modeling_data`是接收方只读验证入口。`python -B -m scripts.run_data_contract_tests`保留旧H04守卫与当前固定基线；当前R7显式绑定非法源行号的阻断诊断修复，完整R6/R5/R4/R3链存于prior_binding，禁止自动刷新。loader另跑独立测试，不在15项合成固定基线内。
- EDA复现使用`scripts/reproduce_data_eda.py`，新结果写`outputs/data_eda/<UTC>/`；展示版在`reports/eda/`。复现另需原始六表，默认ZIP不含原始输入。
- 复用代码在src，命令在scripts，标准/交接在docs，展示报告在reports；新运行仅新UTC目录。变更后验证配置、schema读回、实际输入、相关测试与文档链接。
- 学习型预处理仅训练历史fit，参数/阈值在validation选择；2018已经做描述性EDA，后续须披露。快照不能证明发售前可得、因果或ROI。
- 当前用户已授权清理、制作微信ZIP、审阅并同步现有GitHub仓库。GitHub只提交代码、测试、标准/验收摘要、项目展示的文字摘要及更新日志；原始/正式数据、验收原始JSON、图表/汇总表、ZIP、outputs、.venv、凭据与个人路径保持本地。不直接发送微信消息。
- `docs/NEXT.md`和`docs/JOURNAL.md`仅本地；`JOURNAL.md`为团队发布摘要。完成工作同步内部日记和重要上下文/决议。
