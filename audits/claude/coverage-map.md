# Review coverage map, 2026-11-01

- Present files: 110 (25931 lines; 5 binary; 0 listed but missing on disk)
- No longer present: 0
- Runs recorded: 1; latest `repo-audit-2026-11-01` on 2026-11-01 (110 files, 282 credits)
- Recently reviewed means `last_reviewed` within the 28 days ending 2026-11-01

## Categories

| category | files | lines | reviewed | partially_reviewed | checked_automatically | blocked | excluded_with_reason | inventoried | reviewed or partial, last 28 days | never reviewed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source | 29 | 7800 | 11 | 15 | 3 | 0 | 0 | 0 | 89.7% (26/29) | 10.3% (3/29) |
| tests | 23 | 6296 | 5 | 0 | 18 | 0 | 0 | 0 | 21.7% (5/23) | 78.3% (18/23) |
| saved-results | 23 | 6950 | 23 | 0 | 0 | 0 | 0 | 0 | 100.0% (23/23) | 0.0% (0/23) |
| scripts | 5 | 596 | 3 | 2 | 0 | 0 | 0 | 0 | 100.0% (5/5) | 0.0% (0/5) |
| config | 7 | 1733 | 3 | 4 | 0 | 0 | 0 | 0 | 100.0% (7/7) | 0.0% (0/7) |
| docs | 22 | 2541 | 6 | 8 | 0 | 0 | 0 | 8 | 63.6% (14/22) | 36.4% (8/22) |
| other | 1 | 15 | 1 | 0 | 0 | 0 | 0 | 0 | 100.0% (1/1) | 0.0% (0/1) |

## Source file coverage

| file | line % | branch % | statements | missing lines | branches | missing branches | imported |
|---|---:|---:|---:|---:|---:|---:|---|
| `data-mining-framework/src/invest_mining/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/artifact.py` | 93.10 | 75.00 | 50 | 2 | 8 | 2 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/cli.py` | 97.31 | 95.83 | 300 | 7 | 72 | 3 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/diagnostics.py` | 97.92 | 93.33 | 162 | 2 | 30 | 2 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/expressions.py` | 93.94 | 90.62 | 234 | 11 | 96 | 9 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/inference.py` | 100.00 | 100.00 | 20 | 0 | 2 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/ledger.py` | 98.91 | 98.08 | 132 | 1 | 52 | 1 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/reporting.py` | 100.00 | n/a | 49 | 0 | 0 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-mining-framework/src/invest_mining/search.py` | 96.19 | 92.59 | 156 | 4 | 54 | 4 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/bundle.py` | 88.15 | 85.32 | 415 | 43 | 218 | 32 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/cleaning.py` | 96.80 | 93.33 | 95 | 2 | 30 | 2 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/cli.py` | 91.30 | 81.58 | 123 | 7 | 38 | 7 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/pit.py` | 96.23 | 94.44 | 35 | 1 | 18 | 1 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/schemas.py` | 93.33 | 90.43 | 236 | 13 | 94 | 9 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/sources.py` | 97.60 | 94.74 | 129 | 2 | 38 | 2 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/testing.py` | 100.00 | n/a | 23 | 0 | 0 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `data-pipeline/data-preparation/src/invest_data/yahoo.py` | 90.66 | 80.77 | 205 | 14 | 52 | 10 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/__init__.py` | 100.00 | n/a | 1 | 0 | 0 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/cli.py` | 95.87 | 92.59 | 188 | 6 | 54 | 4 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/config.py` | 96.70 | 92.86 | 140 | 3 | 42 | 3 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/engine.py` | 93.69 | 89.62 | 290 | 14 | 106 | 11 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/metrics.py` | 98.71 | 97.92 | 184 | 2 | 48 | 1 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/quantiles.py` | 97.50 | 93.75 | 192 | 3 | 48 | 3 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/reporting.py` | 97.88 | 93.55 | 174 | 1 | 62 | 4 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/robustness.py` | 94.87 | 91.67 | 27 | 1 | 12 | 1 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/stats.py` | 92.42 | 83.33 | 102 | 5 | 30 | 5 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/strategies.py` | 94.48 | 89.47 | 107 | 4 | 38 | 4 | 2026-11-01 (`repo-audit-2026-11-01`) |
| `strategy-evaluation/src/invest_evaluation/validation.py` | 100.00 | 100.00 | 80 | 0 | 26 | 0 | 2026-11-01 (`repo-audit-2026-11-01`) |

## Least line-covered source files (up to 10)

1. `data-pipeline/data-preparation/src/invest_data/bundle.py`: 88.15%
2. `data-pipeline/data-preparation/src/invest_data/yahoo.py`: 90.66%
3. `data-pipeline/data-preparation/src/invest_data/cli.py`: 91.30%
4. `strategy-evaluation/src/invest_evaluation/stats.py`: 92.42%
5. `data-mining-framework/src/invest_mining/artifact.py`: 93.10%
6. `data-pipeline/data-preparation/src/invest_data/schemas.py`: 93.33%
7. `strategy-evaluation/src/invest_evaluation/engine.py`: 93.69%
8. `data-mining-framework/src/invest_mining/expressions.py`: 93.94%
9. `strategy-evaluation/src/invest_evaluation/strategies.py`: 94.48%
10. `strategy-evaluation/src/invest_evaluation/robustness.py`: 94.87%

## Reading slices

Slice recorded for 2026-11-01:

- `.github/workflows/ci.yml`
- `.gitignore`
- `data-mining-framework/pyproject.toml`
- `data-mining-framework/tests/conftest.py`
- `data-mining-framework/tests/test_cli.py`
- `data-mining-framework/tests/test_diagnostics.py`
- `data-mining-framework/tests/test_evidence.py`
- `data-mining-framework/tests/test_expressions.py`

Next slice (tests, scripts, config; at most 1500 lines; not recorded):

- `data-mining-framework/tests/test_ledger.py` (471 lines)
- `data-mining-framework/tests/test_search_and_inference.py` (156 lines)
- `data-pipeline/data-preparation/tests/test_bundle.py` (229 lines)
- `data-pipeline/data-preparation/tests/test_cleaning_and_sources.py` (383 lines)
- `data-pipeline/data-preparation/tests/test_point_in_time.py` (115 lines)

## No longer present

None.

## Listed but missing on disk

None.

## Coverage paths not in the map

None.

## Either model (by hand, from GPT's `audits/gpt/coverage.csv` at origin/gpt/repo-audits 606eae2, dated 2026-10-31)

- Claude, last 28 days: 81 of 110 tracked files `reviewed` or `partially_reviewed` (73.6 %).
- GPT, 2026-10-31: 42 of 110 (23 reviewed, 19 partially_reviewed).
- Either model: 87 of 110 (79.1 %). GPT adds 6 files Claude only ran or listed: DESIGN_BY_CONTRACT.md, data-pipeline/README.md, data-pipeline/data-preparation/tests/test_bundle.py, docs/ARCHITECTURE.md, docs/REPORTING.md, strategy-evaluation/tests/test_engine.py.
- 23 files neither model has reviewed: these go first on the next run's exploration list (oldest first).
