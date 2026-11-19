# Repository audit coverage

Source `eb64ad8f317fdb81d652a0c2ac1bbcbedd4b63f2` · 2026-11-19. 156 tracked paths, 41334 known unread lines across 123 paths. 1477 newly credited current-blob semantic lines. The inventory gained eight files and changed 28 existing blobs; 2437 old-blob review lines were moved to historical evidence. Five figures have no applicable line count. Peer exact-range union coverage is unavailable.

| Status | Files |
|---|---:|
| inventoried | 81 |
| partially_reviewed | 24 |
| reviewed | 25 |
| checked_automatically | 5 |
| blocked | 21 |

| Category | Files | Known lines | Reviewed or partial | Recent 28 days | Never reviewed |
|---|---:|---:|---:|---:|---:|
| configuration/documentation | 5 | 581 | 2 | 2 | 3 |
| configuration | 7 | 280 | 3 | 4 | 3 |
| documentation | 34 | 3401 | 8 | 8 | 26 |
| source | 12 | 10457 | 2 | 2 | 10 |
| first_party_source | 29 | 9448 | 17 | 20 | 9 |
| source/configuration/documentation | 5 | 464 | 0 | 0 | 5 |
| tests | 24 | 10090 | 8 | 8 | 16 |
| test | 11 | 2356 | 2 | 2 | 9 |
| research_ledger_metadata | 1 | 2 | 1 | 1 | 0 |
| saved_result | 17 | 6948 | 1 | 1 | 16 |
| binary_saved_asset | 5 | 0 | 0 | 0 | 5 |
| script_or_input | 3 | 496 | 3 | 3 | 0 |
| shell_script | 2 | 270 | 2 | 2 | 0 |
| lockfile | 1 | 1517 | 0 | 0 | 1 |

| Largest unread areas | Lines |
|---|---:|
| `audits/gpt/runner/test_guards.py` | 4183 |
| `runs/yahoo-test/2026-10-07/mining/diagnostics/tables/daily_ic.csv` | 3775 |
| `audits/gpt/runner/test_output_collection.py` | 2024 |
| `uv.lock` | 1517 |
| `runs/yahoo-test/2026-10-07/data/market/manifest.json` | 1210 |
| `strategy-evaluation/tests/test_engine.py` | 1198 |
| `data-mining-framework/tests/test_ledger.py` | 1179 |
| `strategy-evaluation/tests/test_stats_and_cli.py` | 1173 |
| `audits/gpt/runner/test_host_safety.py` | 1096 |
| `data-mining-framework/src/invest_mining/cli.py` | 968 |

[Exact ranges](coverage-map.json) · [Field allocation and evidence](2026-11-19-integration/evidence.json)

| Component | Files | Status counts |
|---|---:|---|
| audit_runner | 17 | inventoried 13, partially_reviewed 4 |
| workspace | 42 | inventoried 27, partially_reviewed 6, reviewed 8, checked_automatically 1 |
| mining | 25 | partially_reviewed 6, inventoried 13, reviewed 5, checked_automatically 1 |
| preparation | 17 | reviewed 3, inventoried 9, partially_reviewed 5 |
| data | 6 | inventoried 5, reviewed 1 |
| saved_results | 23 | reviewed 2, blocked 21 |
| evaluation | 26 | inventoried 14, reviewed 6, checked_automatically 3, partially_reviewed 3 |

Current per-file test statement, missing-statement, branch, partial-branch and combined coverage figures are retained in the JSON map where the CI table exposed them. They confer no semantic review credit.
