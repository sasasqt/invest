# Coverage — 2026-11-02

110 tracked blobs inventoried.87 non-data files materialized and byte-verified;23 saved-result/ledger blobs not materialized. Original checkout metadata was not reconstructed. No source byte changed during checks.

Status counts: `{"blocked": 22, "checked_automatically": 20, "inventoried": 8, "partially_reviewed": 24, "reviewed": 36}`. Cumulative exact GPT semantic ranges include the original review, both31October supplements, and today's main/verifier union on identical blobs. Today's primary unique lines: {'exploitation': 1326, 'exploration': 1295}; helper overlap is not counted again in yields. Newly added cumulative GPT ranges: 1832 lines. Remaining: 17827 text lines in 69 paths, plus five binary assets with no semantic review.

| Category | Files | Text lines | GPT semantic lines |
|---|---:|---:|---:|
| binary_saved_asset | 5 | 0 | 0 |
| configuration | 7 | 231 | 176 |
| documentation | 22 | 2541 | 1229 |
| first_party_source | 29 | 7800 | 4884 |
| lockfile | 1 | 1517 | 0 |
| research_ledger_metadata | 1 | 2 | 2 |
| saved_result | 17 | 6948 | 0 |
| script_or_input | 3 | 432 | 326 |
| shell_script | 2 | 164 | 164 |
| tests | 23 | 6296 | 1323 |

Last28days GPT coverage is this saved exact-range union (31October/2November); old dates retained for reused ranges. Either-audit exact union is unavailable: peer file statuses omit per-file blob identity/ranges. GPT is the evidenced lower bound, not a claim of zero peer coverage. Per-file test line/branch coverage was not regenerated or reconstructed from peer summaries; unavailable here.

Ten least semantically covered source files:

- `data-mining-framework/src/invest_mining/__init__.py`: 0/3
- `data-mining-framework/src/invest_mining/diagnostics.py`: 0/315
- `data-pipeline/data-preparation/src/invest_data/__init__.py`: 0/3
- `data-pipeline/data-preparation/src/invest_data/cli.py`: 0/252
- `strategy-evaluation/src/invest_evaluation/__init__.py`: 0/3
- `strategy-evaluation/src/invest_evaluation/cli.py`: 0/378
- `data-mining-framework/src/invest_mining/cli.py`: 96/727
- `data-pipeline/data-preparation/src/invest_data/schemas.py`: 175/544
- `strategy-evaluation/src/invest_evaluation/metrics.py`: 186/491
- `strategy-evaluation/src/invest_evaluation/config.py`: 115/226

Never semantically reviewed in exact GPT records:

- `.gitignore`
- `data-mining-framework/ALPHA_VALIDATION.md`
- `data-mining-framework/LITERATURE_REVIEW.md`
- `data-mining-framework/PRIMARY_SOURCE_CATALOG.md`
- `data-mining-framework/src/invest_mining/__init__.py`
- `data-mining-framework/src/invest_mining/diagnostics.py`
- `data-mining-framework/tests/conftest.py`
- `data-mining-framework/tests/test_cli.py`
- `data-mining-framework/tests/test_diagnostics.py`
- `data-pipeline/data-preparation/src/invest_data/__init__.py`
- `data-pipeline/data-preparation/src/invest_data/cli.py`
- `data-pipeline/data-preparation/tests/test_signal_metadata.py`
- `data-pipeline/data-preparation/tests/test_yahoo.py`
- `docs/QUANTILE_ANALYSIS.md`
- `docs/reviews/README.md`
- `runs/yahoo-test/2026-10-07/README.md`
- `runs/yahoo-test/2026-10-07/data/benchmark/manifest.json`
- `runs/yahoo-test/2026-10-07/data/market/manifest.json`
- `runs/yahoo-test/2026-10-07/eval/config.json`
- `runs/yahoo-test/2026-10-07/eval/figures/diagnostics.png`
- `runs/yahoo-test/2026-10-07/eval/figures/equity_drawdown.png`
- `runs/yahoo-test/2026-10-07/eval/figures/scenarios.png`
- `runs/yahoo-test/2026-10-07/eval/manifest.json`
- `runs/yahoo-test/2026-10-07/eval/metrics.json`
- `runs/yahoo-test/2026-10-07/eval/report.md`
- `runs/yahoo-test/2026-10-07/eval/statistics.json`
- `runs/yahoo-test/2026-10-07/eval/tables/scenarios.csv`
- `runs/yahoo-test/2026-10-07/eval/verdict.json`
- `runs/yahoo-test/2026-10-07/mining/diagnostics/config.json`
- `runs/yahoo-test/2026-10-07/mining/diagnostics/figures/ic.png`
- `runs/yahoo-test/2026-10-07/mining/diagnostics/figures/quantiles.png`
- `runs/yahoo-test/2026-10-07/mining/diagnostics/metrics.json`
- `runs/yahoo-test/2026-10-07/mining/diagnostics/tables/daily_ic.csv`
- `runs/yahoo-test/2026-10-07/mining/diagnostics/tables/tail_returns.csv`
- `runs/yahoo-test/2026-10-07/mining/factor.json`
- `runs/yahoo-test/2026-10-07/signals/manifest.json`
- `runs/yahoo-test/2026-10-07/snapshot/snapshot.json`
- `scripts/sp100_members.txt`
- `strategy-evaluation/examples/quantile_long_short.json`
- `strategy-evaluation/src/invest_evaluation/__init__.py`
- `strategy-evaluation/src/invest_evaluation/cli.py`
- `strategy-evaluation/tests/conftest.py`
- `strategy-evaluation/tests/test_config.py`
- `strategy-evaluation/tests/test_quantiles.py`
- `strategy-evaluation/tests/test_stats_and_cli.py`
- `strategy-evaluation/tests/test_validation.py`
- `tests/test_markdown_links.py`
- `tests/test_quantile_consistency.py`
- `tests/test_save_run.py`
- `uv.lock`

This run's exact slice: 2026-11-02-repro/reading-main.json and verifier-a/read-ranges.json. Next slice: quantiles151–end and callers/tests, schemas176–end plus readers, remaining CLI and diagnostics responsibilities. Complete remaining intervals: [2026-11-02-repro/remaining-semantic-ranges.json](2026-11-02-repro/remaining-semantic-ranges.json). No passing suite or search match is credited as semantic review.
