# IBA6102 Decision Log

Current design version: **v1.1** (frozen 2026-09-24)

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

用户明确指定新提供的2026-09-24会议决议为当前标准，并授权同步本地与云端。上文D-001至D-023为原会议正文，完整保留；本节补充采用、实施与验证说明，不将后来的说明伪装成原会议决议。

- **Current authority:** design v1.1, frozen 2026-09-24. `config.py` 是唯一版本化机器配置源；`docs/PROJECT_CONTEXT.md` 为人读业务摘要。改变设计须先升配置版本并记录决议，再同步代码与说明。
- **Publication scope:** 用户本次明确云端同步授权覆盖D-013中标准/决议文档仅留本地的旧限制。可同步当前会议标准、必要可复现实现及标准说明；docs/NEXT.md、docs/JOURNAL.md内部工作记录维持本地，根JOURNAL.md团队发布摘要可按本次授权同步。D-012及D-013关于原始数据、凭据、个人绝对路径、Notebook输出和运行结果不公开的约束继续生效。本次授权不自动延伸到后续外部动作。
- **Multi-entity implementation:** D-023未指定多实体汇总算子。实现采用 `aggregation="union_prior_games_deduplicated"`：按`;`拆分厂商；在严格较早发行年记录中，匹配任一列出实体的历史游戏取并集，同一历史appid只计一次。命中率=(并集正类数+10×0.10)/(并集游戏数+10)，输出次数为log1p(并集游戏数)。未见或缺失实体回退为次数0、命中率0.10。此为明确的实施约定，不改写D-023原文。
- **Statistical interpretation:** D-014保留了会议当时关于正类率稳定的论证。当前运行解释须注明，同年分位标签本身决定约10%的正类比例，不能据此证明无数据/概念漂移，也不能把质量标签的基准率变化单独当成不能使用它的数学证明。同年排名/分位数减少跨年曝光差异，未消除同年观察时长差异。
- **Historical metrics:** D-017与D-023中的ROC-AUC/AP/Lift及未见厂商比例是原会议引用的历史可行性证据。旧云端alpha=20、历史总体正类率回退、整串实体版本的2018结果为ROC-AUC 0.698359、AP 0.320701、预期Lift@10% 4.078148。它们均不得冒充当前alpha=10、prior=0.10、并集多实体实现的新结果。
- **Current verification:** 新实现通过六表审计、语法检查、四项边界测试和严格JSON输出校验，当前规则指标与独立计算一致。2017历史≤2016，ROC-AUC 0.686476、AP 0.328394、期望Lift@10% 4.225353；2018历史≤2017，ROC-AUC 0.707903、AP 0.336896、期望Lift@10% 4.348139。规则为开发商/发行商平滑命中率平均，Top10%按评分并列的期望选择计算；2018两类厂商均全部未见占57.73%。这是当前滚动规则可行性验证，不是正式ML结果；模型比较仍须统一历史窗口。
- **STEP1 handoff:** `STEP1 OUTPUT/` 的清洗与EDA已完成，但其strict first-rank标签、剔除小样本年份、包含2019的test和特征清单不符合本次采用的v1.1。原交付只读保留作审查依据，不直接作为主模型X/y；不得重跑旧脚本覆盖成果。
- **Snapshot limitation:** 历史编码严格限制所用游戏的发行年份，但这些游戏的命中标签仍取自2019单次快照。结论为回顾性筛选证据，不能声称拥有真实发售前时点可得的完整特征或厂商信誉。

本次采用取代此前“仅以云端main提交68019e6为准”以及“PROJECT_CONTEXT是唯一机器业务配置”的本地约定；既有云端审计与本地清理记录作为历史保留，不再改变当前设计。
