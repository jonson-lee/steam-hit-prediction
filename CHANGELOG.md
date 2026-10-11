# Changelog

All material project updates are recorded here. Raw third-party datasets are not committed.

## 2026-10-12 — Complete v1.2 data handoff and prepare modeling delivery

- Completed the adopted v1.2 parsing/handoff implementation with unchanged v1.1 business rules: inclusive yearly linear-q90 target, chronological train/validation/test, 2019 exclusion, strict feature whitelist and prior-year multi-entity history.
- Final data contains 24,862 developed games / 2,500 positives. Train, validation and test contain 10,345 / 6,357 / 8,160 games; all 2,213 games released in 2019 are excluded.
- Preserved all 21 accepted package files byte-for-byte while relocating them to the private `data/processed/steam_handoff_v12/`. Real-file gates, physical READY and independent consumer acceptance are complete (7/7 official and 29/29 independent checks).
- Added a schema-aware, read-only modeling loader and a Chinese handoff guide. The loader checks READY and configuration, aligns string app IDs, preserves missing/empty sequence states, and exposes exactly 24 predictors separately from labels and metadata.
- Consolidated presentation materials in private `reports/eda/`: 21 summary tables, five PNG/SVG pairs, EDA report and corrected STEP1 claims. Published the prose summary and project file guide.
- Migrated 61 necessary artifacts, then deleted 641 obsolete process files (about 83 MiB), including collaboration experiments/drafts, superseded STEP1 delivery, duplicate candidate files, old outputs and the obsolete notebook.
- Explicit documentation-only R4 bindings preserve all R3 hashes in `prior_binding`. Config, parsing/handoff source, original tests and sealed data are unchanged. No automatic rebaseline.
- Validation: frozen H04 11/11, current contract 150/150 and new loader tests 11/11 passed. Relocated EDA passed 21/21 checks; all 21 CSV and five PNG files match the accepted presentation bytes. ZIP preflight passed CRC, per-file hashes and standalone extracted-package loading.
- The private WeChat ZIP includes the complete data package, reader, standards, acceptance records and presentation materials. Raw inputs, virtual environments, process directories and internal task journals are excluded. Full synthetic tests require a Git clone; the extracted loader does not require Git.
- Modeling, training, tuning and final model evaluation remain unstarted. The 2018 cohort has been inspected descriptively; the snapshot supports a retrospective screening prototype, not sales, causal or ROI claims.

## 2026-10-09 — Adopt the meeting's v1.1 design

- The user explicitly adopted the 2026-09-24 decisions and authorized local/GitHub synchronization.
- Published the authoritative decision log and current design context, with versioned `config.py`.
- Aligned UTC dates, inclusive linear q90 targets, 2019 exclusion, cyclic calendar features, multi-entity prior-year history, and strict feature policy.
- New multi-entity union rule uses alpha=10 and fixed prior=0.10. The 2018 retrospective result is ROC-AUC 0.707903, AP 0.336896, expected Lift@10% 4.348139.
- STEP1 deliveries and raw/generated data stay local. The earlier public-set restriction was superseded only for the explicitly authorized standards and necessary reproducible code.
- Results below are historical and do not describe the current rule implementation.

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
