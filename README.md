# Steam Game Hit Prediction | Steam 游戏爆款预测

IBA6102 Machine Learning for Business 小组项目，面向中小发行商的候选游戏筛选和排序。

**Current standard: v1.1, frozen on 2026-09-24.** The meeting decisions were adopted as the project authority on 2026-10-09. The executable design is defined in `config.py`.

**当前标准：2026-09-24 会议冻结的 v1.1。** 用户于 2026-10-09 指定会议决议为当前标准，并授权同步本地与云端。六表验收与 v1.1 厂商规则复现已完成；STEP1 OUTPUT 已审查，当前主模型接口与正式 ML 流水线待完成。

## Standard and evidence | 标准与证据

| 内容 | 入口 |
|---|---|
| 会议决议原文与实施说明 | [DECISIONS.md](docs/DECISIONS.md) |
| 唯一机器设计配置 | [config.py](config.py) |
| 当前业务标准与进度 | [PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) |
| 数据验收与当前规则指标 | [DATA_AUDIT.md](docs/DATA_AUDIT.md) |
| 商业问题与建模计划 | [项目提案](Project_Proposal_Steam_Game_Success.md) |
| 数据来源、许可与准备 | [data/README.md](data/README.md) |
| 探索入口 | [EDA_Steam.ipynb](EDA_Steam.ipynb) |
| 更新记录 | [JOURNAL.md](JOURNAL.md) |

## Modeling contract | 建模标准

- **Target:** `hit_reviews = 1` iff total ratings reach the within-release-year 90th percentile, using linear interpolation and inclusive `>=`. Small valid cohorts remain labeled; cutoff ties are retained.
- **Split:** train ≤2016, validation 2017, final test 2018. All 2019 releases are excluded. No random split or shuffled CV.
- **History:** split developer/publisher strings on `;`; use strictly earlier release years. Aggregate the union of matching historical games, counting each game once. Use `alpha=10`, fixed prior mean `0.10`, and `log1p` counts. Missing/unseen entities receive count 0 and rate 0.10.
- **Calendar:** UTC date parsing with invalid values logged as `NaT`; month/quarter and cyclic month/day-of-week encodings.
- **Forbidden predictors:** ratings, owners, playtime, SteamSpy tags/tag votes, `tag_count`, and outcome derivatives. IDs, labels, split and release year are association/partition fields.
- **Snapshot sensitivity only:** price, achievements, descriptions, requirements, support, media and their derivatives.
- **Evaluation:** AP/PR-AUC, ROC-AUC, Top10% precision/recall/lift. Transformations fit historical training data; parameters and thresholds are selected on validation.

主标签衡量观测热度，不等于销量、收入、利润或质量。同年分组减少跨年的累积差异，不能消除同年观察时长差异。正类率接近10%由标签设计决定，不能证明没有漂移。

`STEP1 OUTPUT/` 是本地保留的组员交付。其 v1.2 标签、2019 测试范围与 A-only 特征边界不符合当前 v1.1；修正前只供审查参考，不能作为主模型入口。

## Setup and reproducibility | 运行与复现

Python 3.11 or newer, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.data_audit_reproduce
python -m unittest discover -s tests -v
```

Prepare the six CSVs in one directory. The main file is located using `STEAM_DATA_PATH`, `data/raw/steam.csv`, `data/raw/steam_store_games/steam.csv`, then the course-shared `../06_Datasets/steam/steam.csv`. No copy is required when the course data is present.

Raw inputs are read-only. Each run creates `outputs/data_audit/<UTC timestamp>/steam_data_audit.json`. Raw data, STEP1 personal delivery files, generated outputs, virtual environments and credentials remain local.

## Current rule benchmark | 当前规则基准

Retrospective feasibility rule, using the v1.1 multi-entity historical union:

| Evaluation year | ROC-AUC | Average Precision | Expected Lift@10% |
|---|---:|---:|---:|
| 2017 | 0.686476 | 0.328394 | 4.225353 |
| 2018 | 0.707903 | 0.336896 | 4.348139 |

The 2018 rule uses history through 2017. Compare formal ML models against a rule fitted on the same history window. These are feasibility results, not final ML scores.

## Data and limitations | 数据与边界

Source: Nik Davis, [Steam Store Games (Clean dataset)](https://www.kaggle.com/datasets/nikdavis/steam-store-games), CC BY 4.0 as reported by the source metadata. Six CSVs, main table 27,075 ×18, collected around May 2019.

This single snapshot does not prove launch-time attribute values or that historical hit labels were observable at the intended decision date. The project is a retrospective screening prototype; its evidence is non-causal and does not establish ROI.

小组成员姓名与学号不进入公开仓库。后续修改先更新版本配置与决议记录，再同步文档和实现。
