# Repository audit coverage

Source `eb64ad8f317fdb81d652a0c2ac1bbcbedd4b63f2` · 2026-11-24. **156 tracked files, 38,744 known unread lines across 119 paths.** 503 new unique current-blob lines. 5 unknown or non-applicable line counts. Either-audit exact coverage unavailable because peer exact ranges are missing.

| Status | Files |
|---|---:|
| blocked | 21 |
| checked_automatically | 5 |
| inventoried | 60 |
| partially_reviewed | 41 |
| reviewed | 29 |

| Component | Files | Known unread lines |
|---|---:|---:|
| audit_runner | 17 | 10331 |
| workspace | 42 | 4629 |
| mining | 25 | 5960 |
| preparation | 17 | 4209 |
| data | 6 | 289 |
| saved_results | 23 | 6924 |
| evaluation | 26 | 6402 |

| Category | Files | Known lines | With credited ranges | Without |
|---|---:|---:|---:|---:|
| configuration/documentation | 5 | 581 | 2 | 3 |
| configuration | 7 | 280 | 5 | 2 |
| documentation | 34 | 3401 | 10 | 24 |
| source | 12 | 10457 | 2 | 10 |
| first_party_source | 29 | 9448 | 27 | 2 |
| source/configuration/documentation | 5 | 464 | 1 | 4 |
| tests | 24 | 10090 | 13 | 11 |
| test | 11 | 2356 | 3 | 8 |
| research_ledger_metadata | 1 | 2 | 1 | 0 |
| saved_result | 17 | 6948 | 1 | 16 |
| binary_saved_asset | 5 | 0 | 0 | 5 |
| script_or_input | 3 | 496 | 3 | 0 |
| shell_script | 2 | 270 | 2 | 0 |
| lockfile | 1 | 1517 | 0 | 1 |

Current-blob reading in the last 28 days is recorded for 70 files using their last review date. 37 files have no dated semantic review observed in this map. Historical ranges remain attached to their original blobs.

Ten lowest displayed combined line/branch percentages in the matching Python 3.11 job. The gate evaluated full-precision results.

| File | Displayed coverage |
|---|---:|
| data-pipeline/data-preparation/src/invest_data/yahoo.py | 92% |
| data-pipeline/data-preparation/src/invest_data/bundle.py | 93% |
| strategy-evaluation/src/invest_evaluation/stats.py | 95% |
| strategy-evaluation/src/invest_evaluation/strategies.py | 95% |
| data-mining-framework/src/invest_mining/expressions.py | 96% |
| data-mining-framework/src/invest_mining/search.py | 96% |
| data-pipeline/data-preparation/src/invest_data/cleaning.py | 97% |
| strategy-evaluation/src/invest_evaluation/config.py | 97% |
| strategy-evaluation/src/invest_evaluation/engine.py | 97% |
| data-mining-framework/src/invest_mining/cli.py | 98% |

[Exact ranges](coverage-map.json) · [Mining reading](2026-11-24-mining/reading.json) · [CI observations](2026-11-24-mining/ci-observations.json) · [Remaining work](2026-11-24.md)
