# Review coverage map, 2026-11-15

- Present files: 148 (43433 lines; 5 binary; 0 listed but missing on disk)
- No longer present: 0
- Runs recorded: 3; latest `repo-audit-2026-11-15` on 2026-11-15 (148 files, 255 credits)
- Recently reviewed means `last_reviewed` within the 28 days ending 2026-11-15

## Categories

| category | files | lines | reviewed | partially_reviewed | checked_automatically | blocked | excluded_with_reason | inventoried | reviewed or partial, last 28 days | never reviewed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source | 32 | 8750 | 0 | 32 | 0 | 0 | 0 | 0 | 100.0% (32/32) | 0.0% (0/32) |
| tests | 27 | 10291 | 3 | 24 | 0 | 0 | 0 | 0 | 100.0% (27/27) | 0.0% (0/27) |
| saved-results | 23 | 6950 | 23 | 0 | 0 | 0 | 0 | 0 | 100.0% (23/23) | 0.0% (0/23) |
| scripts | 6 | 942 | 3 | 3 | 0 | 0 | 0 | 0 | 100.0% (6/6) | 0.0% (0/6) |
| config | 8 | 1949 | 4 | 0 | 4 | 0 | 0 | 0 | 100.0% (8/8) | 0.0% (0/8) |
| docs | 37 | 4056 | 8 | 27 | 0 | 0 | 0 | 2 | 94.6% (35/37) | 5.4% (2/37) |
| other | 15 | 10495 | 1 | 0 | 12 | 0 | 0 | 2 | 6.7% (1/15) | 93.3% (14/15) |

## Source file coverage

| file | line % | branch % | statements | missing lines | branches | missing branches | imported |
|---|---:|---:|---:|---:|---:|---:|---|
| `data-mining-framework/src/invest_mining/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/artifact.py` | 93.10 | 75.00 | 50 | 2 | 8 | 2 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/cli.py` | 97.70 | 97.41 | 405 | 9 | 116 | 3 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/diagnostics.py` | 98.04 | 93.33 | 174 | 2 | 30 | 2 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/expressions.py` | 93.94 | 90.62 | 234 | 11 | 96 | 9 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/inference.py` | 100.00 | 100.00 | 20 | 0 | 2 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/ledger.py` | 99.06 | 98.39 | 151 | 1 | 62 | 1 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/py.typed` | no data | | | | | | |
| `data-mining-framework/src/invest_mining/reporting.py` | 100.00 | 100.00 | 66 | 0 | 6 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-mining-framework/src/invest_mining/search.py` | 96.23 | 92.59 | 158 | 4 | 54 | 4 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/bundle.py` | 92.46 | 90.27 | 591 | 38 | 298 | 29 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/cleaning.py` | 97.33 | 94.74 | 112 | 2 | 38 | 2 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/cli.py` | 94.95 | 89.58 | 150 | 5 | 48 | 5 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/pit.py` | 96.77 | 95.45 | 40 | 1 | 22 | 1 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/py.typed` | no data | | | | | | |
| `data-pipeline/data-preparation/src/invest_data/schemas.py` | 94.84 | 92.00 | 249 | 10 | 100 | 8 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/sources.py` | 97.71 | 95.00 | 135 | 2 | 40 | 2 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/testing.py` | 100.00 | n/a | 23 | 0 | 0 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `data-pipeline/data-preparation/src/invest_data/yahoo.py` | 92.17 | 85.00 | 221 | 13 | 60 | 9 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/cli.py` | 95.87 | 92.59 | 188 | 6 | 54 | 4 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/config.py` | 96.70 | 92.86 | 140 | 3 | 42 | 3 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/engine.py` | 94.17 | 90.35 | 315 | 14 | 114 | 11 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/metrics.py` | 98.71 | 97.92 | 184 | 2 | 48 | 1 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/py.typed` | no data | | | | | | |
| `strategy-evaluation/src/invest_evaluation/quantiles.py` | 97.50 | 93.75 | 192 | 3 | 48 | 3 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/reporting.py` | 97.88 | 93.55 | 174 | 1 | 62 | 4 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/robustness.py` | 94.87 | 91.67 | 27 | 1 | 12 | 1 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/stats.py` | 92.42 | 83.33 | 102 | 5 | 30 | 5 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/strategies.py` | 94.63 | 90.48 | 107 | 4 | 42 | 4 | 2026-11-15 (`repo-audit-2026-11-15`) |
| `strategy-evaluation/src/invest_evaluation/validation.py` | 100.00 | 100.00 | 80 | 0 | 26 | 0 | 2026-11-15 (`repo-audit-2026-11-15`) |

## Least line-covered source files (up to 10)

1. `data-pipeline/data-preparation/src/invest_data/yahoo.py`: 92.17%
2. `strategy-evaluation/src/invest_evaluation/stats.py`: 92.42%
3. `data-pipeline/data-preparation/src/invest_data/bundle.py`: 92.46%
4. `data-mining-framework/src/invest_mining/artifact.py`: 93.10%
5. `data-mining-framework/src/invest_mining/expressions.py`: 93.94%
6. `strategy-evaluation/src/invest_evaluation/engine.py`: 94.17%
7. `strategy-evaluation/src/invest_evaluation/strategies.py`: 94.63%
8. `data-pipeline/data-preparation/src/invest_data/schemas.py`: 94.84%
9. `strategy-evaluation/src/invest_evaluation/robustness.py`: 94.87%
10. `data-pipeline/data-preparation/src/invest_data/cli.py`: 94.95%

## Reading slices

Slice recorded for 2026-11-15:

- `data-pipeline/data-preparation/tests/test_dataset_keys.py`
- `data-pipeline/data-preparation/tests/test_signal_metadata.py`
- `data-pipeline/data-preparation/tests/test_yahoo_symbols.py`
- `strategy-evaluation/tests/conftest.py`
- `strategy-evaluation/tests/test_config.py`
- `strategy-evaluation/tests/test_metrics.py`
- `strategy-evaluation/tests/test_quantiles.py`

Next slice (tests, scripts, config; at most 1500 lines; not recorded):

- `data-mining-framework/pyproject.toml` (17 lines)
- `data-pipeline/data-preparation/pyproject.toml` (13 lines)
- `strategy-evaluation/pyproject.toml` (17 lines)

## No longer present

None.

## Listed but missing on disk

None.

## Coverage paths not in the map

None.
