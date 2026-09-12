# Steam Data

## Source and license

- Dataset: [Steam Store Games (Clean dataset)](https://www.kaggle.com/datasets/nikdavis/steam-store-games)
- Creator: Nik Davis
- Collection: Steam Store API plus SteamSpy API, gathered around May 2019
- License reported by Kaggle metadata: Attribution 4.0 International (CC BY 4.0)
- Creator methodology: [data collection](https://nik-davis.github.io/posts/2019/steam-data-collection/), [Steam cleaning](https://nik-davis.github.io/posts/2019/steam-data-cleaning/), and [SteamSpy cleaning](https://nik-davis.github.io/posts/2019/steamspy-data-cleaning/)

The accepted local source was the course archive:

```text
6102-Machine-Learning-for-Business/06_Datasets/datasetSteam.zip
```

The ZIP integrity test passed, and each extracted CSV's size and CRC matched its ZIP member. The project-local copies are in `data/raw/steam_store_games/` and match the accepted SHA-256 fingerprints.

## File inventory

| File | Rows × columns | Role | Main-key coverage |
|---|---:|---|---:|
| `steam.csv` | 27,075 × 18 | Required main modeling table | 100% |
| `steam_description_data.csv` | 27,334 × 4 | Optional text sensitivity analysis | 100% |
| `steam_media_data.csv` | 27,332 × 5 | Optional media metadata | 100% |
| `steam_requirements_data.csv` | 27,319 × 6 | Optional requirements text | 99.95% |
| `steam_support_info.csv` | 27,136 × 4 | Optional support metadata | 99.28% |
| `steamspy_tag_data.csv` | 29,022 × 372 | Post-release tag votes; forbidden in primary model | 100% |

All six tables have complete, unique app IDs and no exact duplicate rows. The main table has only fifteen missing cells: one `developer` and fourteen `publisher` values.

## Modeling contract

Use releases through 2018 only. The 2019 cohort is incomplete.

Primary target:

```text
total_ratings = positive_ratings + negative_ratings
hit_reviews = total_ratings >= within-release-year 90th percentile
```

Target/outcome columns must never enter the predictors:

- `positive_ratings`, `negative_ratings`, `owners`;
- `average_playtime`, `median_playtime`;
- `steamspy_tags` and the 371 tag-vote columns.

See `Project_Proposal_Steam_Game_Success.md` and `docs/DATA_AUDIT.md` for the accepted feature and time-split policy.

## Re-run validation

From the project root:

```powershell
python .\scripts\validate_steam_data.py --output .\data\audit\steam_data_audit.json
```

Expected headline result:

```text
file_integrity: PASS
analytical_acceptance: CONDITIONAL_GO
```

Raw files are intentionally ignored by `.gitignore`. Do not upload the raw data to a repository or external platform as part of this project workflow.
