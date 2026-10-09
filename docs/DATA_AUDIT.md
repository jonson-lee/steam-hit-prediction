# Steam Dataset Acceptance and v1.1 Rule Report

Updated: 2026-10-09. Current standard: the 2026-09-24 meeting's **v1.1**, explicitly adopted by the user. See [DECISIONS.md](DECISIONS.md), [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) and [config.py](../config.py).

## Verdict and data quality

**File integrity: PASS. Analytical acceptance: CONDITIONAL_GO.** The six-file Nik Davis Steam dataset supports a retrospective classification/ranking prototype. It does not prove launch-time feature values or deployment-time availability of historical hit labels.

The accepted course ZIP passes integrity testing; the extracted six CSVs match ZIP size/CRC and accepted SHA-256 fingerprints. Main table: 27,075 rows ×18 columns. Every table has unique, complete app IDs and no exact duplicate rows. The main table has 1 missing developer and 14 missing publishers; release dates and owner ranges parse successfully, rating counts are nonnegative, and every game has at least one rating.

Whitespace-only entity names are missing for history encoding. Six additional publisher strings contain only whitespace; they do not create a shared Unknown history group.

Auxiliary coverage: descriptions/media/tags 100%; requirements 27,062 of 27,075 (13 missing); support 26,881 (194 missing). Extra auxiliary IDs are reported separately.

## Target and chronological cohorts

`total_ratings = positive_ratings + negative_ratings`. Use the full valid release-year cohort's 90th percentile with `interpolation="linear"`, retaining `>=` boundary ties and small cohorts. Do not force exactly 10% using file order.

All 2,213 releases from incomplete 2019 are excluded and have no modeling label. Invalid dates are logged as UTC NaT and remain unlabeled.

| Split | Release year | Rows | Positives |
|---|---|---:|---:|
| Train | ≤2016 | 10,345 | 1,046 |
| Validation | 2017 | 6,357 | 637 |
| Final test | 2018 | 8,160 | 817 |
| Development total | ≤2018 | 24,862 | 2,500 |

The label measures observed traction, not sales, revenue, profit or quality. Near-10% prevalence follows from label design and does not prove no drift. Same-year comparisons reduce cross-year exposure differences without eliminating unequal within-year observation windows.

## Feature and history contract

- Primary: English flag, developer/publisher, platforms, age requirement, categories/genres, month/quarter and cyclic month/day-of-week features.
- Historical encoding: split and deduplicate semicolon entities; use strictly earlier release years. Matching historical games form a union, with each game counted once. Output dev/pub log1p counts and smoothed hit rates using alpha=10, fixed prior mean=0.10. Missing/unseen entities receive count0 and rate0.10.
- Snapshot sensitivity only: price, achievements, descriptions, requirements, support, media and their derivatives.
- Forbidden: ratings, owners, playtime, SteamSpy tags/votes, tag_count, outcome derivatives and targets. IDs, name, release year and split are metadata, not predictors.

`config.assert_primary_feature_columns()` rejects any non-whitelisted primary input before learned expansion. Dates are parsed as UTC; malformed values are coerced to NaT and explicitly reported.

## Current retrospective rule

Multi-entity aggregation is the deduplicated union of matching historical games. Each rate is `(union_hits + 10*0.10)/(union_count + 10)`; the rule score averages developer and publisher rates. Ranking cutoff ties receive expected selection weight.

| Evaluation year | History through | ROC-AUC | AP | Expected precision@10% | Expected recall@10% | Expected lift@10% |
|---|---|---:|---:|---:|---:|---:|
| 2017 | 2016 (10,345 games) | 0.686476 | 0.328394 | 0.423399 | 0.422735 | 4.225353 |
| 2018 | 2017 (16,702 games) | 0.707903 | 0.336896 | 0.435347 | 0.434814 | 4.348139 |

In 2018, 57.73% of games have neither a previously observed developer nor publisher and receive the same prior score. Product descriptors remain necessary. The 2018 rule includes 2017 history; formal ML comparisons must use the same fit window.

Historical hit labels still come from the 2019 snapshot. This is a retrospective feasibility benchmark, not proof that the same reputation information was known before release.

The earlier whole-string, alpha=20 rule used historical prevalence as its prior and produced 2018 ROC-AUC 0.698359, AP 0.320701 and expected Lift@10% 4.078148. Meeting D-017/D-023 cites historical values; those are preserved as historical evidence. The original meeting's lift4.64 is not the output of the current tie-aware implementation.

## STEP1 and reproducibility

STEP1 OUTPUT completed cleaning, derived fields, EDA and label exploration; its CSVs reproduce its v1.2 script. Strict first-rank labels, small-cohort exclusion, test including2019, SteamSpy tags/tag_count and snapshot fields conflict with the adopted v1.1. The original delivery remains local for review and is not a current modeling handoff. Supervised X/y and formal ML pipelines remain to be built.

From the repository root:

```bash
python -m src.data_audit_reproduce
python -m unittest discover -s tests -v
```

Input discovery is documented in [data/README.md](../data/README.md). Each audit creates a new UTC directory under outputs/data_audit. Raw files and generated results remain local.

Verification covers actual six-file hashes/structure, versioned label/split counts, UTC invalid dates, calendar cycles, same-year/future exclusion, multi-entity deduplication, missing-entity fallback, whitelist rejection, output preservation and independent row-level history/rule reproduction.

## Source notes

- [Kaggle dataset and source metadata](https://www.kaggle.com/datasets/nikdavis/steam-store-games)
- [Creator collection methodology](https://nik-davis.github.io/posts/2019/steam-data-collection/)
- [SteamSpy cleaning notes](https://nik-davis.github.io/posts/2019/steamspy-data-cleaning/)
- [SteamSpy limitations](https://steamspy.com/about)
