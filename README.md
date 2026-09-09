# Steam 游戏爆款预测

课程项目（IBA6102 Machine Learning for Business，CUHK-Shenzhen）

**问题**：中小型发行商如何用"发售前可得的信息"判断一款 Steam 游戏能否成为爆款，从而决定预算投向。

- 团队：7 人
- 数据：Kaggle「Steam Store Games (Clean dataset)」约 27,000 款游戏（2019 快照）
- 方法：监督学习二分类（Logistic Regression → Decision Tree → Random Forest → XGBoost）

## 仓库结构

```
data/                          # 数据目录（不入库，见下方说明）
Project_Proposal_Steam_Game_Success.md   # 提案：商业问题 / 标签定义 / A-B 字段划分
EDA_Steam.ipynb                # EDA：字段核对、清洗、标签不平衡度摸底
JOURNAL.md                     # 更新日记
```

## 数据准备（克隆后第一步）

本仓库用 `.gitignore` 排除了数据文件，克隆后请自行准备数据：

1. 从 Kaggle 下载 [Steam Store Games](https://www.kaggle.com/datasets/nikdavis/steam-store-games)
2. 把 `steam.csv` 放到本仓库的 `data/` 目录（没有就新建）
3. 打开 `EDA_Steam.ipynb` → **Run All**

> 若 `data/steam.csv` 不存在，notebook 会回退到本机开发机的绝对路径并打印提示。

## 方法纪律

- **特征只用发售时可得信息（A 类字段）**，见提案 §4
- `positive_ratings` / `negative_ratings` / `owners` / `average_playtime` / `median_playtime`（B 类）**仅用于构造标签**，绝不进入 X（数据泄漏红线）
- 评估只报 AUC / precision / recall / F1 + confusion matrix，不报裸 accuracy

## 协作约定

- 直接 push 到 `main`（小组规模小）；大改动建议先开 Issue 讨论
- 每人更新 `JOURNAL.md` 记录进展；结论性发现同步更新提案
- 图表、结论产出到 `notebooks/`（后面加）
