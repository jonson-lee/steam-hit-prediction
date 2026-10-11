# IBA6102 Decision Log

Current policy version: **v1.2** (adopted 2026-10-11); unchanged business base **v1.1** (frozen 2026-09-24)

## 2026-09-12 — Data acceptance

| ID | Decision | Rationale |
|---|---|---|
| D-001 | Accept the six-file Nik Davis Steam dataset with a **Conditional Go**. | Files, schema, keys, dates, joins, and license passed; the original target and feature claims require correction. |
| D-002 | Use release-year top-decile total rating count as the primary `hit` target. | It is exact in this snapshot, has negligible cutoff ties, and keeps the positive rate near 10% across cohorts. It is a traction proxy, not sales. |
| D-003 | Do not use year-wise top 10% of SteamSpy owner midpoints as the primary target. | `owners` has only 13 bands. Inclusive 90th-percentile labeling yields 20.97% positives overall and 100% for the incomplete 2019 cohort. Arbitrary tie-breaking would manufacture precision not present in the source. |
| D-004 | Retain `owners` only as an ordinal robustness outcome. | SteamSpy reports estimates and explicitly warns that small/recent games are unreliable; ownership is not the same as sales. |
| D-005 | Exclude all 2019 releases from model development. | The snapshot ends on 2019-05-01, so the cohort is incomplete and has uneven outcome maturity. |
| D-006 | Use chronological train/validation/test cohorts: through 2016 / 2017 / 2018. | The intended use is prediction for future releases; random splitting would mix time periods and overstate generalization. |
| D-007 | Exclude SteamSpy tags and tag votes from every pre-release model. | Tags are community-voted after release. Their identities and vote counts are future information at the stated decision point. |
| D-008 | Treat price, achievement count, descriptions, requirements, media, and support fields as snapshot-only sensitivity features. | The dataset does not preserve their historical launch-time values. |
| D-009 | Encode developer/publisher history using past releases only. | Full-dataset frequency, target, or reputation encoding would leak future cohort information. |
| D-010 | Evaluate Average Precision/PR-AUC, ROC-AUC, and top-10% precision, recall, and lift; do not lead with accuracy. | The positive class is approximately 10%. The business decision is ranking a limited candidate portfolio. |
| D-011 | Compare models with a time-safe prior developer/publisher rule. | A simple historical rule already provides a meaningful benchmark, so a complex model must demonstrate incremental value. |
| D-012 | Keep raw CSV files local and excluded from version control; do not upload or submit externally. | This follows the user's instruction and avoids accidental third-party-data publication. |
| D-013 | Restrict any public GitHub update to the minimum reproducible project set. | Internal context/decision/next files, the machine-generated audit JSON, and the redundant changelog remain local; the public set contains no raw data, credentials, absolute local paths, or notebook outputs. |

## 2026-09-24 — v1.1 design reconciliation

A team meeting reviewed the "核心决策说明（新手版）" draft, which proposed the pre-freeze alternatives. Each conflict was re-decided on the record; the frozen direction was retained on the substantive points and three additive improvements were adopted.

| ID | Decision | Rationale |
|---|---|---|
| D-014 | Keep release-year top-decile total rating count as the primary `hit`; keep the rating-ratio label only as an optional secondary sensitivity outcome. | The ratio label is unstable for small samples (2,906 games at ratio 1.0 have a median of 4 ratings) and measures product sentiment, not the high-traction screening target in the business decision. Under a fixed `>0.8` threshold its positive rate also drifts from 61% (2007) to 13% (2018), while the heat label stays at 10.0-10.1% every year; a drifting base rate cannot serve a chronological split as the primary target. Reaffirms D-002. |
| D-015 | Keep the three chronological cohorts (through 2016 / 2017 / 2018) and the exclusion of all 2019 releases; reject the binary `<2018` / `>=2018` split. | A binary split would fold the incomplete 2019 cohort into the test set and remove the independent validation cohort. Reaffirms D-005 and D-006. |
| D-016 | Keep `price` and `achievements` as snapshot-only sensitivity features; reject promoting them into the primary feature set. | The snapshot does not preserve launch-time values, so primary use would mix in non-reproducible information. Reaffirms D-008. |
| D-017 | Keep developer/publisher history as a primary feature, encoded from prior releases only (walk-forward). | It is the strongest time-safe signal; the 2018 benchmark reaches ROC-AUC 0.698, AP 0.321, and Lift@10% 4.08. Reaffirms D-009. |
| D-018 | Add cyclic (sin/cos) encoding for release month and day-of-week alongside the calendar and quarter features. | Avoids imposing a false linear order on cyclical calendar features at negligible cost. |
| D-019 | Adopt a single versioned design config (`config.py`) as the only source of truth; any design change must bump the version and be logged here. | Prevents silent edits and test-set tuning, and keeps code and docs aligned. |
| D-020 | Parse `release_date` as UTC and coerce invalid values to `NaT`, logging them explicitly. | Removes timezone ambiguity and avoids silently dropping malformed rows. |
| D-021 | Pin target threshold semantics: `hit_reviews = 1` if and only if `total_ratings >=` the 90th percentile of the full release-year population (inclusive, computed per year, 2019 excluded; ties retained; cutoff method recorded in `config.py`). | Removes the `>` versus `>=` ambiguity and the population-choice ambiguity flagged in the draft. |
| D-022 | Use `linear` interpolation (pandas default) for the per-year 90th-percentile cutoff, keep inclusive `>=`, and label small pre-2007 cohorts as-is. | A probe of all five pandas methods gave identical cutoffs and a ~10.0% positive rate for every cohort from 2014 onward; differences appear only in cohorts with n<30 (1997-2005, 26 games), where `lower` over-labels. Linear is the standard definition and is tie-light at the boundary. |
| D-023 | Fix the developer/publisher history encoding: split multi-entity strings on `;` and aggregate across all listed entities; use strictly earlier release years; emit `dev_prior_count`, `dev_prior_hit_rate`, `pub_prior_count`, `pub_prior_hit_rate` (`log1p` counts); Bayesian-smooth rates with fixed `alpha=10` and prior mean 0.10; unseen or missing entities get count 0 and the prior mean. | Reproduces the 2018 feasibility AUC 0.698. `alpha` is insensitive (AUC 0.696-0.699, lift 4.64 for alpha 1-50), and 68.4% of 2018 developers are unseen, so smoothing is required. Detail for D-009. |

## Superseded proposal assumptions

- The topic is no longer tentative.
- The quality label `positive_rate >= 0.85` is no longer a candidate primary hit definition.
- Random split and ordinary shuffled cross-validation are not permitted.
- `steamspy_tags`, current price, and achievement count are not automatically classified as verified pre-release features.
- The 2026-09-24 "新手版" draft assumptions are superseded by v1.1: the rating-ratio primary label, the binary 2018 split, primary use of price/achievements, and the omission of `steamspy_tags` from the blacklist are all rejected.

## 2026-10-09 — User adoption and implementation record

用户明确指定2026-09-24会议冻结v1.1为当前标准，并授权同步本地与现有云端仓库。D-001至D-023为原会议正文，以上逐字保留；本节及后续记录为后来采纳和实施说明，不改写会议原文。

- **标准来源：** [config.py](../config.py)为唯一版本化机器配置源；[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)为当前业务摘要。改变设计须先升配置版本并记录决议，再同步实现和文档。
- **公开范围：** 此次明确云端同步授权覆盖D-013中标准和决议文档仅留本地的旧限制。当前标准、必要可复现代码及标准说明可公开；内部待办和日记维持本地。原始数据、运行证据、凭据、个人绝对路径和Notebook输出不公开的约束继续有效。
- **多实体约定：** D-023未指定汇总算子，实施采用`union_prior_games_deduplicated`：匹配任一实体的严格较早发行年游戏取并集，同一历史appid只计一次。输出为`log1p(N)`和`(H + 10 × 0.10) / (N + 10)`，未见或缺失回退0和0.10。
- **统计解释：** 约10%的正类率由同年分位标签设计决定，不能证明无漂移；同年比较减少跨年累积差异，不能消除同年观察时长差异。质量标签基准率变化不能单独作为不可采用的数学证明。
- **历史指标：** D-017/D-023为原会议可行性结果；旧alpha=20、历史总体正类率回退及整串实体实现的2018 ROC-AUC 0.698359、AP 0.320701、期望Lift@10% 4.078148保持历史身份。当前并集规则实测为2017 ROC-AUC 0.686476、AP 0.328394、Lift 4.225353；2018 ROC-AUC 0.707903、AP 0.336896、Lift 4.348139。2018历史包含2017，Top10%按评分并列期望选择计算；这些不是正式ML成绩。
- **快照限制：** 历史发行年隔离不能证明真实预测时点已能观察到相同命中标签和厂商信誉。结论为回顾性筛选证据，不建立销量、因果效果或ROI。

本次采用取代此前“仅以旧云端提交为准”及“PROJECT_CONTEXT是唯一机器配置”的约定；历史记录不改变当前机器标准。

## 2026-10-10 — Execution limited to data production

用户明确“不要推进到建模，我们目前制作数据部分的任务”。范围为数据预检、清洗和EDA、标签和时间切分、字段边界、appid对齐及X/y交接；X/y为数据产物，不代表已启动训练、调参或评估。模型依赖缺口留待建模阶段处理，不阻塞数据制作。

## 2026-10-11 — B05 policy adoption (v1.2)

用户对B05推荐方案明确回答“采用推荐方案”。该授权采纳解析和交接政策，不改变会议v1.1业务参数。

| ID | 采纳决定 | 边界 |
|---|---|---|
| D-024 | 采用`steam-parse/v1`：appid为strip后的ASCII数字字符串，保留前导零，精确Int64存储上界，逐表唯一性/碰撞；english精确0/1，required_age非负精确整数及Unicode十进制词法；逐字段缺失词作用范围、不新增na；五序列分号拆分、原拼写首见去重、未知token保留，平台按大小写不敏感完整token判定；缺失派生count0/hasFalse且保留源态 | config升v1.2，不改变D-001至D-023；不学习补值或词表，不以2018选择规则，年龄只设存储上界、不设未经采用的语义cap。 |
| D-025 | 采用`steam-handoff/v1`：CSV+JSON-in-cell、序列态旁表、raw原值/源身份、完整cohort人口、精确ratings及安全加法；坏键、基础人口非法ratings、非法特征阻断；未覆盖年份隔离且保留人口；稳定层→manifest→report→READY，消费者后验包外保存 | NaT/2019/未知年不丢原记录，不缩人口重算cutoff。缺失序列null/S_MISSING，派生视为空；非缺失零实体[]/S_EMPTY_LIST，缺失子类保留；['']仅为表示例，不是合法源解析结果。 |
| D-026 | 历史继续冻结窗口A：严格较早发行年、并集去重、alpha10/prior0.10/log1p；保留小cohort、UTC/coerce/mixed、linear q90/inclusive、时间切分及24特征白名单 | 封顶2016的窗口B不采用、不生产、不作门禁；raw_provenance、快照敏感性及CURRENT_HANDOFF默认OFF。 |
| D-027 | 政策采纳、只读诊断、实现合成验收、正式文件验收分别记录 | 当次政策采纳不冒称实现、PASS或READY。该阶段的“未实施”描述为历史事实；后续实现与正式验收分别见D-028/D-029。 |

当前定版入口为[解析合同](DATA_PARSE_CONTRACT.md)、[交接合同](DATA_HANDOFF_CONTRACT.md)、[字段字典](data_contract/field_dictionary.csv)及[机器schema](data_contract/handoff_schema.json)。B05推荐、回传及候选来源属于当时过程记录，清理不改变已采用的规则。

## 2026-10-11 — Contract implementation and fixed baseline

| ID | 决定 | 边界 |
|---|---|---|
| D-028 | 用户授权实现已定版B05合同，保留旧H04源码、fixture、测试及SHA守卫，新增v1.2固定哈希基线并实际运行53P05/68H05；新增独立解析、构造、读回和消费者路径，旧H04用冻结v1.1配置在临时副本运行 | 当次只做实现与合成验收，正式制作另需授权。config的`implemented_real_file_acceptance_pending`为当时绑定状态，不能覆盖后来真实验收结论。政策/业务规则不变，不静默重绑。 |

实现和测试入口见[DATA_CONTRACT_IMPLEMENTATION.md](DATA_CONTRACT_IMPLEMENTATION.md)。R2旧H04 11/11、当前148/148为历史合成结果；真实制作必要修复后的R3旧11/11、当前150/150分别记录。

## 2026-10-11 — Real-file production and independent acceptance

| ID | 决定 | 边界 |
|---|---|---|
| D-029 | 用户明确授权按B05正式制作、真实门禁、保护六输入和旧STEP1、使用新UTC目录；全部适用门禁通过后生成物理READY，并完成独立消费者核验。该任务已完成，见[正式验收摘要](DATA_HANDOFF_ACCEPTANCE.md) | 政策v1.2/业务v1.1不变；SteamSpy原生appid适配及真实规模历史验收修复显式绑定R3，旧H04不变。模型训练、调参、评估未启动，可选接口和指针仍OFF；当次未进行Git提交或发布。 |

随后用户授权数据阶段EDA和交接说明，完成21张汇总表、5对PNG/SVG及STEP1结论修正。2018描述性分布和标签人口已查看，未据此选择规则、特征、参数或阈值；后续建模保留查看历史。

## 2026-10-12 — Project cleanup, handoff and GitHub review

| ID | 决定 | 边界 |
|---|---|---|
| D-030 | 用户授权整理项目，仅保留建模和展示所需文件，删除过期或过程文件；列出微信交接文件；整理后审阅并同步现有GitHub仓库版本，撰写更新日志。正式21文件按原字节迁入`data/processed/steam_handoff_v12/`，必要验收证据归入`data/processed/acceptance/`，最终EDA归入`reports/eda/`；生成私下交接ZIP | 课程原始六表不删除，封存文件不改字节；旧STEP1、旧outputs、协作实验、过时根决议及旧Notebook按授权清理。公开集限当前标准、代码、测试和说明，数据/运行证据/压缩包、内部待办和日记、凭据及个人信息保持本地。此次授权不包含我们训练、调参或评估模型。 |

本轮两个合同和assertion_index只修正当前阶段说明及删除来源的引用，显式R4保留R3 prior_binding与三个旧hash；config、实现、测试和封存21文件不变。公开文档链接指向可追踪标准或交接指南，本地证据以代码路径说明。接收方按[MODELING_HANDOFF.md](MODELING_HANDOFF.md)核验并使用正式数据。
