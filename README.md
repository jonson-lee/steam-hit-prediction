# Steam 游戏爆款预测

课程项目（IBA6102 Machine Learning for Business，CUHK-Shenzhen）

**问题**：中小型发行商如何用发行决策时可获得、且在数据中相对稳定的产品属性，筛选更可能进入同年高市场热度组的 Steam 游戏，从而安排有限的尽调与发行预算。

- 团队：7 人
- 状态：题目已锁定；数据验收 **Conditional Go**
- 数据：Kaggle「Steam Store Games (Clean dataset)」27,075 款游戏（2019 快照，CC BY 4.0）
- 方法：时间安全规则基线 → Logistic Regression → 一个树集成模型

## 仓库结构

```
data/                          # 原始数据、本地审计快照与数据说明
docs/                          # 项目上下文、决策、下一步和数据验收报告
scripts/validate_steam_data.py # 可重复执行的数据验收脚本
Project_Proposal_Steam_Game_Success.md   # 提案：商业问题 / 标签定义 / A-B 字段划分
EDA_Steam.ipynb                # EDA（待按验收结论重构）
JOURNAL.md                     # 更新日记
```

## 数据与验收

当前机器上的六张 CSV 已放入 `data/raw/steam_store_games/`，并通过哈希、ZIP、字段、主键、重复、缺失、日期、标签和表间覆盖检查。原始数据由 `.gitignore` 排除，不上传。

复验命令：

```powershell
python .\scripts\validate_steam_data.py --output .\data\audit\steam_data_audit.json
```

详见 `data/README.md` 和 `docs/DATA_AUDIT.md`。

## 方法纪律

- 主标签：各发行年份内 `positive_ratings + negative_ratings` 达到第 90 百分位；2019 年排除
- `positive_ratings`、`negative_ratings`、`owners`、playtime 和 SteamSpy tags/tag votes 绝不进入 X
- 价格、成就、描述、配置和媒体字段只作快照敏感性分析
- 训练/验证/测试按时间切分：≤2016 / 2017 / 2018，禁止随机切分
- 主报 Average Precision/PR-AUC、ROC-AUC、Top 10% precision/recall/lift，不以 accuracy 作为主指标
- 数据是 2019 单次快照；结论是回顾性筛选证据，不是因果、销量、收入或 ROI 结论

## 协作约定

- 直接 push 到 `main`（小组规模小）；大改动建议先开 Issue 讨论
- 每人更新 `JOURNAL.md` 记录进展；结论性发现同步更新提案
- 图表、结论产出到 `notebooks/`（后面加）
