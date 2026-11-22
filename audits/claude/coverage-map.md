# Review coverage map, 2026-11-22

- Present files: 156 (46310 lines; 5 binary; 0 listed but missing on disk)
- No longer present: 0
- Runs recorded: 4; latest `repo-audit-2026-11-22` on 2026-11-22 (156 files, 254 credits)
- Recently reviewed means `last_reviewed` within the 28 days ending 2026-11-22

## Categories

| category | files | lines | reviewed | partially_reviewed | checked_automatically | blocked | excluded_with_reason | inventoried | reviewed or partial, last 28 days | never reviewed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source | 32 | 9448 | 0 | 29 | 0 | 0 | 0 | 3 | 100.0% (32/32) | 0.0% (0/32) |
| tests | 35 | 12446 | 7 | 28 | 0 | 0 | 0 | 0 | 100.0% (35/35) | 0.0% (0/35) |
| saved-results | 23 | 6950 | 23 | 0 | 0 | 0 | 0 | 0 | 100.0% (23/23) | 0.0% (0/23) |
| scripts | 6 | 944 | 2 | 3 | 0 | 0 | 0 | 1 | 100.0% (6/6) | 0.0% (0/6) |
| config | 8 | 1949 | 0 | 5 | 3 | 0 | 0 | 0 | 100.0% (8/8) | 0.0% (0/8) |
| docs | 37 | 4078 | 0 | 37 | 0 | 0 | 0 | 0 | 100.0% (37/37) | 0.0% (0/37) |
| other | 15 | 10495 | 2 | 1 | 10 | 0 | 0 | 2 | 20.0% (3/15) | 80.0% (12/15) |

## Source file coverage

| file | line % | branch % | statements | missing lines | branches | missing branches | imported |
|---|---:|---:|---:|---:|---:|---:|---|
| `data-mining-framework/src/invest_mining/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/artifact.py` | 100.00 | 100.00 | 50 | 0 | 8 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/cli.py` | 97.92 | 97.66 | 448 | 9 | 128 | 3 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/diagnostics.py` | 100.00 | 100.00 | 174 | 0 | 30 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/expressions.py` | 96.44 | 95.67 | 466 | 15 | 208 | 9 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/inference.py` | 100.00 | 100.00 | 20 | 0 | 2 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/ledger.py` | 99.06 | 98.39 | 151 | 1 | 62 | 1 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/py.typed` | no data | | | | | | |
| `data-mining-framework/src/invest_mining/reporting.py` | 100.00 | 100.00 | 66 | 0 | 6 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-mining-framework/src/invest_mining/search.py` | 96.24 | 92.59 | 159 | 4 | 54 | 4 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/bundle.py` | 92.69 | 90.60 | 591 | 37 | 298 | 28 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/cleaning.py` | 97.33 | 94.74 | 112 | 2 | 38 | 2 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/cli.py` | 97.98 | 95.83 | 150 | 2 | 48 | 2 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/pit.py` | 100.00 | 100.00 | 40 | 0 | 22 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/py.typed` | no data | | | | | | |
| `data-pipeline/data-preparation/src/invest_data/schemas.py` | 100.00 | 100.00 | 249 | 0 | 100 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/sources.py` | 100.00 | 100.00 | 135 | 0 | 40 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/testing.py` | 100.00 | n/a | 23 | 0 | 0 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `data-pipeline/data-preparation/src/invest_data/yahoo.py` | 92.17 | 85.00 | 221 | 13 | 60 | 9 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/cli.py` | 99.17 | 98.15 | 188 | 1 | 54 | 1 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/config.py` | 96.70 | 92.86 | 140 | 3 | 42 | 3 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/engine.py` | 96.75 | 95.59 | 356 | 10 | 136 | 6 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/metrics.py` | 98.72 | 97.92 | 186 | 2 | 48 | 1 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/py.typed` | no data | | | | | | |
| `strategy-evaluation/src/invest_evaluation/quantiles.py` | 97.50 | 93.75 | 192 | 3 | 48 | 3 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/reporting.py` | 98.03 | 94.12 | 186 | 1 | 68 | 4 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/robustness.py` | 100.00 | 100.00 | 27 | 0 | 12 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/stats.py` | 94.70 | 88.24 | 117 | 4 | 34 | 4 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/strategies.py` | 94.63 | 90.48 | 107 | 4 | 42 | 4 | 2026-11-22 (`repo-audit-2026-11-22`) |
| `strategy-evaluation/src/invest_evaluation/validation.py` | 100.00 | 100.00 | 80 | 0 | 26 | 0 | 2026-11-22 (`repo-audit-2026-11-22`) |

## Least line-covered source files (up to 10)

1. `data-pipeline/data-preparation/src/invest_data/yahoo.py`: 92.17%
2. `data-pipeline/data-preparation/src/invest_data/bundle.py`: 92.69%
3. `strategy-evaluation/src/invest_evaluation/strategies.py`: 94.63%
4. `strategy-evaluation/src/invest_evaluation/stats.py`: 94.70%
5. `data-mining-framework/src/invest_mining/search.py`: 96.24%
6. `data-mining-framework/src/invest_mining/expressions.py`: 96.44%
7. `strategy-evaluation/src/invest_evaluation/config.py`: 96.70%
8. `strategy-evaluation/src/invest_evaluation/engine.py`: 96.75%
9. `data-pipeline/data-preparation/src/invest_data/cleaning.py`: 97.33%
10. `strategy-evaluation/src/invest_evaluation/quantiles.py`: 97.50%

## Reading slices

Slice recorded for 2026-11-22:

- `data-mining-framework/tests/test_coverage_mining.py`
- `data-mining-framework/tests/test_scale_check.py`
- `data-pipeline/data-preparation/tests/test_coverage_data_cli.py`
- `data-pipeline/data-preparation/tests/test_coverage_schemas.py`
- `data-pipeline/data-preparation/tests/test_coverage_sources_and_pit.py`
- `strategy-evaluation/tests/test_benchmark_delistings.py`

Next slice (tests, scripts, config; at most 1500 lines; not recorded):

- `uv.lock` (1517 lines)

## No longer present

None.

## Listed but missing on disk

None.

## Coverage paths not in the map

None.
