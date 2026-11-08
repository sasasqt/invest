<!-- generated read-only mirror of audits/claude/coverage-map.md, run repo-audit-2026-11-08 -->
# Review coverage map, 2026-11-08

- Present files: 111 (26940 lines; 5 binary; 0 listed but missing on disk)
- No longer present: 0
- Runs recorded: 2; latest `repo-audit-2026-11-08` on 2026-11-08 (111 files, 255 credits)
- Recently reviewed means `last_reviewed` within the 28 days ending 2026-11-08

## Categories

| category | files | lines | reviewed | partially_reviewed | checked_automatically | blocked | excluded_with_reason | inventoried | reviewed or partial, last 28 days | never reviewed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source | 29 | 7958 | 4 | 17 | 8 | 0 | 0 | 0 | 93.1% (27/29) | 6.9% (2/29) |
| tests | 24 | 7069 | 6 | 6 | 12 | 0 | 0 | 0 | 62.5% (15/24) | 37.5% (9/24) |
| saved-results | 23 | 6950 | 23 | 0 | 0 | 0 | 0 | 0 | 100.0% (23/23) | 0.0% (0/23) |
| scripts | 5 | 659 | 3 | 0 | 0 | 0 | 0 | 2 | 100.0% (5/5) | 0.0% (0/5) |
| config | 7 | 1733 | 2 | 0 | 5 | 0 | 0 | 0 | 100.0% (7/7) | 0.0% (0/7) |
| docs | 22 | 2556 | 4 | 4 | 0 | 0 | 0 | 14 | 68.2% (15/22) | 31.8% (7/22) |
| other | 1 | 15 | 1 | 0 | 0 | 0 | 0 | 0 | 100.0% (1/1) | 0.0% (0/1) |

## Source file coverage

| file | line % | branch % | statements | missing lines | branches | missing branches | imported |
|---|---:|---:|---:|---:|---:|---:|---|
| `data-mining-framework/src/invest_mining/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/artifact.py` | 93.10 | 75.00 | 50 | 2 | 8 | 2 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/cli.py` | 96.98 | 96.15 | 320 | 9 | 78 | 3 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/diagnostics.py` | 98.04 | 93.33 | 174 | 2 | 30 | 2 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/expressions.py` | 93.94 | 90.62 | 234 | 11 | 96 | 9 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/inference.py` | 100.00 | 100.00 | 20 | 0 | 2 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/ledger.py` | 98.91 | 98.08 | 132 | 1 | 52 | 1 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/reporting.py` | 100.00 | 100.00 | 66 | 0 | 6 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-mining-framework/src/invest_mining/search.py` | 94.31 | 88.89 | 157 | 6 | 54 | 6 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/bundle.py` | 88.15 | 85.32 | 415 | 43 | 218 | 32 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/cleaning.py` | 96.80 | 93.33 | 95 | 2 | 30 | 2 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/cli.py` | 91.30 | 81.58 | 123 | 7 | 38 | 7 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/pit.py` | 96.23 | 94.44 | 35 | 1 | 18 | 1 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/schemas.py` | 93.33 | 90.43 | 236 | 13 | 94 | 9 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/sources.py` | 97.60 | 94.74 | 129 | 2 | 38 | 2 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/testing.py` | 100.00 | n/a | 23 | 0 | 0 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `data-pipeline/data-preparation/src/invest_data/yahoo.py` | 90.66 | 80.77 | 205 | 14 | 52 | 10 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/cli.py` | 95.87 | 92.59 | 188 | 6 | 54 | 4 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/config.py` | 96.70 | 92.86 | 140 | 3 | 42 | 3 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/engine.py` | 93.83 | 89.62 | 299 | 14 | 106 | 11 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/metrics.py` | 98.71 | 97.92 | 184 | 2 | 48 | 1 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/quantiles.py` | 97.50 | 93.75 | 192 | 3 | 48 | 3 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/reporting.py` | 97.88 | 93.55 | 174 | 1 | 62 | 4 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/robustness.py` | 94.87 | 91.67 | 27 | 1 | 12 | 1 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/stats.py` | 92.42 | 83.33 | 102 | 5 | 30 | 5 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/strategies.py` | 94.48 | 89.47 | 107 | 4 | 38 | 4 | 2026-11-08 (`repo-audit-2026-11-08`) |
| `strategy-evaluation/src/invest_evaluation/validation.py` | 100.00 | 100.00 | 80 | 0 | 26 | 0 | 2026-11-08 (`repo-audit-2026-11-08`) |

## Least line-covered source files (up to 10)

1. `data-pipeline/data-preparation/src/invest_data/bundle.py`: 88.15%
2. `data-pipeline/data-preparation/src/invest_data/yahoo.py`: 90.66%
3. `data-pipeline/data-preparation/src/invest_data/cli.py`: 91.30%
4. `strategy-evaluation/src/invest_evaluation/stats.py`: 92.42%
5. `data-mining-framework/src/invest_mining/artifact.py`: 93.10%
6. `data-pipeline/data-preparation/src/invest_data/schemas.py`: 93.33%
7. `strategy-evaluation/src/invest_evaluation/engine.py`: 93.83%
8. `data-mining-framework/src/invest_mining/expressions.py`: 93.94%
9. `data-mining-framework/src/invest_mining/search.py`: 94.31%
10. `strategy-evaluation/src/invest_evaluation/strategies.py`: 94.48%

## Reading slices

Slice recorded for 2026-11-08:

- `data-mining-framework/tests/test_ledger.py`
- `data-mining-framework/tests/test_reporting.py`
- `data-mining-framework/tests/test_search_and_inference.py`
- `data-pipeline/data-preparation/tests/test_bundle.py`
- `data-pipeline/data-preparation/tests/test_cleaning_and_sources.py`
- `data-pipeline/data-preparation/tests/test_point_in_time.py`

Next slice (tests, scripts, config; at most 1500 lines; not recorded):

- `data-pipeline/data-preparation/tests/test_signal_metadata.py` (288 lines)
- `strategy-evaluation/tests/conftest.py` (19 lines)
- `strategy-evaluation/tests/test_config.py` (73 lines)
- `strategy-evaluation/tests/test_metrics.py` (186 lines)
- `strategy-evaluation/tests/test_quantiles.py` (439 lines)

## No longer present

None.

## Listed but missing on disk

None.

## Coverage paths not in the map

None.
