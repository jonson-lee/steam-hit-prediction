# Changelog

All material project updates are recorded here. Raw third-party datasets are not committed.

## 2026-09-12 — Steam data acceptance and design freeze

### Added

- Reproducible full-data validator: `scripts/validate_steam_data.py`.
- Data provenance, inventory, license, and usage contract in `data/README.md`.
- Formal acceptance evidence in `docs/DATA_AUDIT.md`.
- Minimal runtime dependencies in `requirements.txt`.
- `.gitignore` rules preventing raw data, credentials, local configuration, and runtime artifacts from entering version control.

### Validated

- All six CSV files match the accepted SHA-256 fingerprints and original ZIP members.
- The 27,075-row main table has a complete and unique `appid`, no exact duplicate rows, and only fifteen missing cells.
- Auxiliary tables cover between 99.28% and 100% of main-table games.
- All release dates and SteamSpy owner intervals parse successfully.

### Changed

- Project status changed from tentative to topic locked with conditional data acceptance.
- Primary target changed from the tentative quality/owner alternatives to release-year top-decile total rating volume.
- The incomplete 2019 cohort was excluded from model development.
- Validation changed to chronological cohorts: through 2016 for training, 2017 for validation, and 2018 for final testing.
- SteamSpy tags and tag votes were reclassified as forbidden post-release predictors.
- Price, achievement count, descriptions, requirements, support, and media were limited to snapshot sensitivity analyses.
- The proposal, README, EDA notebook, decision log, and work plan were synchronized with the accepted design.

### Feasibility result

A time-safe historical developer/publisher rule achieved the following on the 2018 cohort:

- ROC-AUC: 0.698
- Average Precision: 0.321
- Tie-aware expected Lift@10%: 4.08

This is a data-feasibility benchmark, not a final model result.

### Evidence boundary

- The target represents high observed Steam engagement, not sales, revenue, profit, product quality, or causal impact.
- The source is a May 2019 snapshot and does not prove that every attribute equals its value at the original launch date.

### Public-release review

- No raw CSV or ZIP archive is included.
- No credential, API key, token, absolute machine path, notebook output, or notebook attachment is included.
- Internal project context, decision, next-action, and machine-generated audit files remain local.
