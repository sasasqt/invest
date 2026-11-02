# Coverage map —31October2026

All110tracked files inventoried and byte-verified. Semantic coverage is incomplete. Automatic identity/AST/TOML/shell checks are not review.

{'reviewed': 23, 'inventoried': 27, 'partially_reviewed': 19, 'checked_automatically': 41}

| Category | Files | Text lines | Semantically read GPT lines |
|---|---:|---:|---:|
| binary_saved_asset | 5 | 0 | 0 |
| configuration | 7 | 231 | 176 |
| documentation | 22 | 2541 | 1107 |
| first_party_source | 29 | 7800 | 3159 |
| lockfile | 1 | 1517 | 0 |
| research_ledger_metadata | 1 | 2 | 2 |
| saved_result | 17 | 6948 | 0 |
| script_or_input | 3 | 432 | 326 |
| shell_script | 2 | 164 | 164 |
| tests | 23 | 6296 | 612 |

Primary unique reading:5023lines; GPT main+VerifierA union:5546lines. Last28days: these exact same-content ranges read today only; no prior published audit evidence. Either-audit coverage has this GPT lower bound, with Claude coverage unknown, never substituted as zero.

Never semantically reviewed in available state:

- `.gitignore`
- `data-mining-framework/ALPHA_VALIDATION.md`
- `data-mining-framework/LITERATURE_REVIEW.md`
- `data-mining-framework/PRIMARY_SOURCE_CATALOG.md`
- `data-mining-framework/src/invest_mining/__init__.py`
- `data-mining-framework/src/invest_mining/artifact.py`
- `data-mining-framework/src/invest_mining/cli.py`
- `data-mining-framework/src/invest_mining/diagnostics.py`
- `data-mining-framework/src/invest_mining/ledger.py`
- `data-mining-framework/src/invest_mining/reporting.py`
- `data-mining-framework/tests/conftest.py`
- `data-mining-framework/tests/test_cli.py`
- `data-mining-framework/tests/test_diagnostics.py`
- `data-mining-framework/tests/test_evidence.py`
- `data-mining-framework/tests/test_ledger.py`
- `data-mining-framework/tests/test_search_and_inference.py`
- `data-pipeline/data-preparation/src/invest_data/__init__.py`
- `data-pipeline/data-preparation/src/invest_data/cli.py`
- `data-pipeline/data-preparation/src/invest_data/schemas.py`
- `data-pipeline/data-preparation/src/invest_data/sources.py`
- `data-pipeline/data-preparation/src/invest_data/testing.py`
- `data-pipeline/data-preparation/tests/test_cleaning_and_sources.py`
- `data-pipeline/data-preparation/tests/test_point_in_time.py`
- `data-pipeline/data-preparation/tests/test_signal_metadata.py`
- `data-pipeline/data-preparation/tests/test_yahoo.py`
- `docs/HISTORICAL_BASELINE.md`
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
- `strategy-evaluation/src/invest_evaluation/quantiles.py`
- `strategy-evaluation/src/invest_evaluation/reporting.py`
- `strategy-evaluation/src/invest_evaluation/robustness.py`
- `strategy-evaluation/tests/conftest.py`
- `strategy-evaluation/tests/test_config.py`
- `strategy-evaluation/tests/test_metrics.py`
- `strategy-evaluation/tests/test_quantiles.py`
- `strategy-evaluation/tests/test_stats_and_cli.py`
- `strategy-evaluation/tests/test_validation.py`
- `tests/test_markdown_links.py`
- `tests/test_pipeline.py`
- `tests/test_quantile_consistency.py`
- `tests/test_save_run.py`
- `uv.lock`

Ten least semantically covered first-party source files (ties path-sorted):

- `data-mining-framework/src/invest_mining/__init__.py`: 0/3 lines
- `data-mining-framework/src/invest_mining/artifact.py`: 0/72 lines
- `data-mining-framework/src/invest_mining/cli.py`: 0/727 lines
- `data-mining-framework/src/invest_mining/diagnostics.py`: 0/315 lines
- `data-mining-framework/src/invest_mining/ledger.py`: 0/249 lines
- `data-mining-framework/src/invest_mining/reporting.py`: 0/72 lines
- `data-pipeline/data-preparation/src/invest_data/__init__.py`: 0/3 lines
- `data-pipeline/data-preparation/src/invest_data/cli.py`: 0/252 lines
- `data-pipeline/data-preparation/src/invest_data/schemas.py`: 0/544 lines
- `data-pipeline/data-preparation/src/invest_data/sources.py`: 0/229 lines

Exact remaining intervals: [remaining-semantic-ranges.json](2026-10-31-repro/remaining-semantic-ranges.json). Next slice: schemas.py→CLI consumers, ledger.py→artifact.py, evaluation config/quantiles/reporting and respective tests. Bundle failure/race leads and Yahoo malformed snapshot shapes remain unchecked concerns, not findings. Per-category binary counts carry no invented line totals.
