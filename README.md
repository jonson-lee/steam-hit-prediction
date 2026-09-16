# Steam Game Hit Prediction

> Screening candidate games for a small or medium-sized publisher.
> IBA6102 Machine Learning for Business — group project.
>
> 面向中小型发行商的 Steam 游戏爆款筛选模型。IBA6102《商业机器学习》小组课程项目。

---

## Overview | 项目概述

**EN** — A small or medium-sized publisher has more candidate games than it can fund, so it needs a
pre-release screening score to rank candidates for deeper due diligence and budget allocation.
This project estimates whether a candidate game is likely to enter the high-traction group among
games released in the same calendar year. It is a decision-support tool, not an automatic green-light
system.

**中文** — 中小型发行商可选的游戏数量远超其能投入发行/代理的项目，因此需要在**发售前**用一个筛选
分数对候选游戏排序，以便安排有限的尽调与预算。本项目预测一款候选游戏能否进入"同年发行游戏中的高热度
组"。它是决策支持工具，不是自动放行系统。

---

## Data and license | 数据与许可

- **Source:** Nik Davis, *Steam Store Games (Clean dataset)* — combining Steam Store and SteamSpy API data.
- **License:** CC BY 4.0.
- **Shape:** six CSV files; main table 27,075 games × 18 columns; snapshot collected around May 2019.
- **Access:** raw CSVs are **not** committed. Download from Kaggle and place them under
  `data/raw/steam_store_games/` before running the validator.
- Provenance, inventory, and licensing notes live in `data/README.md`; formal acceptance evidence
  lives in `docs/DATA_AUDIT.md`.

> 原始 CSV 不入库，需自行从 Kaggle 下载到 `data/raw/steam_store_games/`。数据来源、清单与许可说明见
> `data/README.md`，正式验收证据见 `docs/DATA_AUDIT.md`。

---

## Repository structure | 仓库结构

```
data/
  README.md                      # data provenance, inventory, license, usage contract
  raw/                           # raw CSVs (git-ignored, local only)
  audit/                         # machine-readable audit JSON (local)
docs/
  DATA_AUDIT.md                  # formal data acceptance evidence
scripts/
  validate_steam_data.py         # reproducible full-data validator
EDA_Steam.ipynb                  # exploratory analysis (to be rebuilt on the locked design)
Project_Proposal_Steam_Game_Success.md  # proposal: business problem, labels, A/B field split
CHANGELOG.md                     # material changes over time
JOURNAL.md                       # short progress log
requirements.txt                 # runtime dependencies
```

---

## Method and label policy | 方法与标签口径

- **Primary target:** `hit_reviews = 1` when total rating count
  (`positive_ratings + negative_ratings`) is at or above the 90th percentile within its release-year
  cohort; otherwise 0. The incomplete 2019 cohort is excluded.
- **Time split:** train ≤ 2016, validation 2017, final test 2018. Random splitting is prohibited.
- **Forbidden predictors (leakage):** `positive_ratings`, `negative_ratings`, `owners`,
  `average_playtime`, `median_playtime`, and all SteamSpy tag / tag-vote columns.
- **Snapshot-only sensitivity features:** `price`, `achievements`, descriptions, requirements,
  support info, and media-derived features.
- **Evaluation:** Average Precision / PR-AUC, ROC-AUC, and precision / recall / lift among the top 10%
  of scored candidates. Accuracy is not a primary metric.

> 主标签为"同年发行游戏总评价数 ≥ 90 分位"，排除 2019；时间切分 ≤2016 / 2017 / 2018；评价数、销量、
> 游玩时长与 SteamSpy 标签一律禁止作为特征（防泄漏）。

---

## Setup and reproducibility | 环境与复现

```powershell
python -m pip install -r requirements.txt
python .\scripts\validate_steam_data.py --output .\data\audit\steam_data_audit.json
```

---

## Results | 结果

Data-feasibility benchmark (not a final model result). A time-safe historical developer/publisher
rule achieved, on the 2018 cohort:

| Metric | Value |
|---|---|
| ROC-AUC | 0.698 |
| Average Precision | 0.321 |
| Tie-aware expected Lift@10% | 4.08 |

---

## Limitations | 局限

- The source is a single May 2019 snapshot; snapshot fields may not equal their values at launch.
- The target measures observed Steam engagement, not sales, revenue, profit, quality, or causal impact.
- SteamSpy `owners` is an estimate with only 13 coarse intervals and is used for sensitivity only.

> 数据为 2019 年单次快照；标签反映的是 Steam 热度而非销量、收入或产品质量；结论仅为回顾性筛选证据，
> 不构成因果或 ROI 主张。

---

## Team | 团队

Group coursework project. Member names and student IDs are intentionally omitted from this repository;
the focus is on the project itself.

> 小组课程项目。为保护隐私，仓库不包含成员姓名与学号，内容仅聚焦项目本身。

## Acknowledgements | 致谢

Steam Store Games dataset by Nik Davis (CC BY 4.0); built for the IBA6102 course.
