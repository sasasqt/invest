# Repository audit coverage

Source `eb64ad8f317fdb81d652a0c2ac1bbcbedd4b63f2` · 2026-11-21. **156 tracked paths; 40367 unread known lines across 120 paths.** 967 newly credited current-blob semantic lines this visit. Inventory/source unchanged from19Nov. Five binary figures have no applicable line count. Peer current-blob exact-range union is unavailable; either-audit coverage is unknown. No full-file runtime claim follows from static reading.

| Status | Files |
|---|---:|
| blocked | 21 |
| checked_automatically | 5 |
| inventoried | 77 |
| partially_reviewed | 25 |
| reviewed | 28 |

| Category | Files | Known lines | Reviewed or partial | Recent28 days | Never reviewed current bytes |
|---|---:|---:|---:|---:|---:|
| configuration/documentation | 5 | 581 | 2 | 2 | 3 |
| configuration | 7 | 280 | 3 | 3 | 4 |
| documentation | 34 | 3401 | 8 | 8 | 26 |
| source | 12 | 10457 | 2 | 2 | 10 |
| first_party_source | 29 | 9448 | 20 | 20 | 9 |
| source/configuration/documentation | 5 | 464 | 0 | 0 | 5 |
| tests | 24 | 10090 | 9 | 9 | 15 |
| test | 11 | 2356 | 2 | 2 | 9 |
| research_ledger_metadata | 1 | 2 | 1 | 1 | 0 |
| saved_result | 17 | 6948 | 1 | 1 | 16 |
| binary_saved_asset | 5 | 0 | 0 | 0 | 5 |
| script_or_input | 3 | 496 | 3 | 3 | 0 |
| shell_script | 2 | 270 | 2 | 2 | 0 |
| lockfile | 1 | 1517 | 0 | 0 | 1 |

| Largest unread areas | Lines |
|---|---:|
| `audits/gpt/runner/test_guards.py` | 4065 |
| `runs/yahoo-test/2026-10-07/mining/diagnostics/tables/daily_ic.csv` | 3775 |
| `audits/gpt/runner/test_output_collection.py` | 2024 |
| `uv.lock` | 1517 |
| `runs/yahoo-test/2026-10-07/data/market/manifest.json` | 1210 |
| `strategy-evaluation/tests/test_engine.py` | 1198 |
| `data-mining-framework/tests/test_ledger.py` | 1179 |
| `strategy-evaluation/tests/test_stats_and_cli.py` | 1173 |
| `audits/gpt/runner/test_host_safety.py` | 1096 |
| `audits/gpt/runner/isolated_runner.py` | 920 |

| Component | Files | Status counts |
|---|---:|---|
| audit_runner | 17 | {'inventoried': 13, 'partially_reviewed': 4} |
| workspace | 42 | {'inventoried': 27, 'partially_reviewed': 5, 'reviewed': 9, 'checked_automatically': 1} |
| mining | 25 | {'partially_reviewed': 7, 'inventoried': 10, 'reviewed': 7, 'checked_automatically': 1} |
| preparation | 17 | {'reviewed': 3, 'inventoried': 9, 'partially_reviewed': 5} |
| data | 6 | {'inventoried': 5, 'reviewed': 1} |
| saved_results | 23 | {'reviewed': 2, 'blocked': 21} |
| evaluation | 26 | {'inventoried': 13, 'reviewed': 6, 'checked_automatically': 3, 'partially_reviewed': 4} |

[Exact ranges and retained per-file CI line/branch coverage](coverage-map.json) · [This visit and next slice](2026-11-21-performance/reading.json). Per-file normal-CI counts remain exact-source historical results, not semantic review credit. Next slice: complete bundle/export expected schemas and trial-count consumer trace before qualified negative controls.
