# Reporting and visualizations

Reporting consumes saved numerical results. It must not quietly recompute metrics with different assumptions or rerun mining to render a chart.

## Ownership

Planned code locations:

```text
data-mining-framework/src/invest_mining/reporting/
  plots/                    # IC, quantiles, decay, redundancy, robustness
strategy-evaluation/src/invest_evaluation/reporting/
  plots/                    # Equity, drawdown, trades, costs, exposures
```

Calculation stays in `diagnostics/` or `metrics/`; plotting and report assembly stay in `reporting/`. Extract a small shared formatting utility only when actual duplication warrants it. A future cross-component dashboard should read report artifacts rather than import either training or simulation internals.

## Output arrangement

```text
artifacts/<component>/<run-id>/
  manifest.json
  config.json
  metrics.json
  verdict.json              # evaluation: factor evidence and portfolio verdict, separately
  tables/
  figures/
  report.html
```

Generated artifacts are ignored by Git. Small synthetic/golden fixtures remain under tracked `tests/fixtures/`. Preserve valuable research outputs in an artifact store or deliberate archive; `.gitignore` is not persistence or backup.

Each immutable run manifest identifies input dataset/signal/model/strategy versions, code revision, resolved configuration, split/scenario definitions, timestamps, seeds, and content checksums. Save the underlying tables needed to reproduce figures. Do not write credential values into configurations or provenance.

Strategy reports show factor confirmation and portfolio validation as separate verdicts. The factor verdict is the evidence published with the signals (`factor_evidence` in the [data contract](DATA_CONTRACT.md)), copied without change; the portfolio verdict comes from rules declared in the strategy configuration. Neither may be merged into or override the other ([strategy evaluation](../strategy-evaluation/README.md#factor-and-portfolio-verdicts)).

New `verdict.json` files use `verdict_version = 2`: mandatory solvency and base-net-Sharpe validity checks accompany the configurable rules. Known insolvency is rejected regardless of positive bootstrap/DSR statistics or disabled stress checks. V1 saved reports can still be rendered; rerun evaluation for the corrected verdict. Factor evidence uses its own version 2, bound to both factor identity and tested horizon; see [migration instructions](DATA_CONTRACT.md#signal-confirmation-evidence).

Use interactive HTML for exploration and SVG/PDF/PNG for shareable outputs. Reports need units, time ranges, gross/net labels, benchmarks, sample counts, and missing/undefined-result explanations. Distinguish training, validation, and confirmation visually; uncertainty and unfavorable results should not disappear through axis choices or omitted groups.

## Initial chart sets

- **Mining:** IC/rank IC over time, rolling effects and intervals, [quantile profiles](QUANTILE_ANALYSIS.md), decay by horizon, coverage, correlation clusters, and robustness scenarios.
- **Strategy evaluation:** net/gross equity and benchmark, drawdowns and recovery, calendar returns, trade/return distributions, exposure/concentration, turnover/cost decomposition, and delay/capacity stress results.

Keep chart generation deterministic from saved inputs. Test figure inputs, labels, units, and report structure with small fixtures; avoid brittle pixel snapshots unless visual regressions justify them.
