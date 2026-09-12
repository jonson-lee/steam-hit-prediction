# Steam Dataset Acceptance Report

Audit date: 2026-09-12

## Verdict

**Conditional Go.** The data acquisition and file-quality gates pass. The dataset is sufficient for a small, rigorous IBA6102 classification and ranking project after revising the target, time split, and feature boundary described below.

It does not support a literal claim that every predictor was captured before each game's release. It supports a retrospective prototype using relatively stable store metadata, evaluated on later release cohorts.

## Acquisition and rights

The complete dataset was already present in the local course archive, so no Kaggle login or new scraping was required. Acquisition difficulty is therefore low for this machine and moderate for a new teammate who must download it from Kaggle.

Kaggle metadata identifies the dataset as *Steam Store Games (Clean dataset)*, reports 252,037,780 bytes and a CC BY 4.0 license, and says it was gathered around May 2019. The creator documents collection from the Steam Store and SteamSpy APIs. No files were uploaded or submitted during this audit.

## Integrity and structural quality

| Check | Result |
|---|---:|
| Required CSV files present | 6 of 6 |
| Project-copy SHA-256 matches accepted source | 6 of 6 |
| Original ZIP test | Pass |
| Extracted size/CRC matches ZIP | 6 of 6 |
| Main table | 27,075 rows × 18 columns |
| Main `appid` nulls / duplicates | 0 / 0 |
| Exact duplicate rows | 0 in every table |
| Main missing values | 1 developer; 14 publishers |
| Release-date parse failures | 0 |
| Owner-range parse failures / invalid bounds | 0 / 0 |
| Negative rating counts | 0 |
| Games with zero total ratings | 0 |

Auxiliary-table coverage of the 27,075 main games is excellent: 100% for descriptions, media, and tags; 99.95% for requirements; and 99.28% for support information.

## Target acceptance

### Rejected primary target: owners midpoint top 10%

`owners` contains only 13 interval values. Applying an inclusive 90th-percentile cutoff within each release year produces 5,678 positives, or 20.97% of all records, rather than approximately 10%. For the incomplete 2019 cohort every game falls in the lowest interval, so the inclusive method labels 100% as hits. Exact 10% selection would require arbitrary tie-breaking among games that the source cannot distinguish.

SteamSpy also describes owners as extrapolated estimates, warns that small and recent games are unreliable, and states that “owned” is not equivalent to “sold.” Owners therefore remains a secondary ordinal robustness outcome only.

### Accepted primary target: rating-volume cohort top decile

The accepted target is whether `positive_ratings + negative_ratings` reaches the 90th percentile within the same release year. Cutoff ties are negligible, and the positive rate is stable:

| Cohort | Rows | Positive rate |
|---|---:|---:|
| Train, through 2016 | 10,345 | 10.11% |
| Validation, 2017 | 6,357 | 10.02% |
| Test, 2018 | 8,160 | 10.01% |

This is a popularity/market-traction proxy, not sales, revenue, profit, quality, or causal impact.

The rank correlation between rating volume and the owner-band midpoint is 0.733, so the target is directionally related to ownership while avoiding the owner's extreme interval ties.

## Leakage and timestamp audit

The source is a single 2019 snapshot. It does not preserve the value of the store page at the time each game launched.

- Safe for the primary model, subject to time-safe encoding: release timing, English flag, developer, publisher, platform, age requirement, categories, and genres.
- Sensitivity only: current price, achievement count, descriptions, requirements, support, and media metadata.
- Forbidden: ratings, owners, playtime, and SteamSpy tags/tag votes.

Tags are community-voted and therefore post-release. Developer/publisher reputation features must be calculated from earlier releases only.

## Feasibility smoke test

A deliberately simple rule scored each future game by Bayesian-smoothed historical hit rates for its developer and publisher. It used no future cohort labels.

| Evaluation cohort | ROC-AUC | Average Precision | Tie-aware expected Lift@10% |
|---|---:|---:|---:|
| 2017 | 0.667 | 0.308 | 3.89 |
| 2018 | 0.698 | 0.321 | 4.08 |

The random Average Precision baseline is approximately 0.10. This smoke test shows usable historical signal and justifies proceeding to Logistic Regression and one regularized tree ensemble. It is a feasibility result, not the final model score.

The main remaining challenge is cold start: 68.4% of 2018 developers and 62.1% of 2018 publishers were unseen in earlier cohorts. Genre, category, platform, and other product descriptors are therefore necessary.

## Conditions for use

1. Exclude 2019 from training and testing.
2. Use chronological cohorts; do not use random splitting or shuffled cross-validation.
3. Fit all transformations using past data only.
4. Keep post-release fields and SteamSpy tags out of predictors.
5. Present the target as high observed traction, not commercial sales.
6. Compare every ML model against the historical developer/publisher rule.
7. Describe any snapshot-only feature experiment as sensitivity analysis.

## Reproducibility

Run:

```powershell
python .\scripts\validate_steam_data.py --output .\data\audit\steam_data_audit.json
```

The validator checks fingerprints, schema, primary keys, duplicates, dates, owner ranges, table coverage, target behavior, time splits, and the rule-based signal benchmark.

## Source notes

- [Kaggle dataset page](https://www.kaggle.com/datasets/nikdavis/steam-store-games)
- [Creator's data-collection methodology](https://nik-davis.github.io/posts/2019/steam-data-collection/)
- [Creator's SteamSpy cleaning notes](https://nik-davis.github.io/posts/2019/steamspy-data-cleaning/)
- [SteamSpy methodology and limitations](https://steamspy.com/about)
