# Invest

Invest is co-developed by human contributors, GPT, and Claude.

A modular Python investment research framework made of three independently installable components, each in its own top-level folder (`data-pipeline/data-preparation/`, `data-mining-framework/`, `strategy-evaluation/`). A first end-to-end baseline is implemented and tested: publish a dataset, mine and confirm factors, export frozen signals, and backtest them with explicit execution timing, costs, metrics, statistics, stress scenarios and figures. The next milestone is a reproducible experiment on historical data, starting with Yahoo Finance as a test-only source; see the [roadmap](ROADMAP.md). Development may use feature, experiment, or release branches as appropriate; the folder layout does not require all work to happen on `main`.

## Components

- [Data preparation](data-pipeline/data-preparation/README.md): download, clean, preprocess, and publish CSV, SQLite or Parquet datasets.
- [Strategy evaluation](strategy-evaluation/README.md): apply trading rules to supplied data/signals and evaluate portfolio performance after costs.
- [Data mining framework](data-mining-framework/README.md): consume published datasets for factor discovery, model training, inference, and signal diagnostics.

The components exchange artifacts through a [versioned dataset contract](docs/DATA_CONTRACT.md). They do not depend on each other's private implementation; any shared public contract/runtime utility must have an explicit versioned interface. Each component has its own Python package, dependency configuration, and tests. See the [architecture guide](docs/ARCHITECTURE.md) for the folder layout and ownership boundaries.

## Development guidelines

Read [Python Development Guidelines](PYTHON_GUIDELINES.md) for the recommended project structure, extensibility practices, dependency management, coding standards, and testing workflow.

Read [Git Development Guidelines](GIT_GUIDELINES.md) for branch naming, focused commits, pull requests, history management, conflict resolution, and safe collaboration.

Read [CI/CD Guidelines](CI_CD_GUIDELINES.md) for what CI checks, pinned and least-privilege workflows, release versioning and publishing, and reproducible research runs.

Read [Design by Contract Guidelines](DESIGN_BY_CONTRACT.md) for preconditions, postconditions, invariants, failure guarantees, boundary validation, numerical contracts, and interchangeable implementation tests.

Read [Rapid Software Development Guidelines](RAPID_DEVELOPMENT.md) for small working increments, bounded experiments, fast feedback, proportionate validation, technical debt management, and reliable research iteration.

The shared [quantile analysis](docs/QUANTILE_ANALYSIS.md) and [reporting](docs/REPORTING.md) specifications cover bucket comparisons, visualization ownership, and generated artifacts. The architecture guide lists the prerequisites for the first runnable end-to-end workflow.

Each component folder has a `src` package layout, its own `pyproject.toml`, and pytest tests under `tests/`. The root `pyproject.toml` defines the uv workspace, the shared dev tools (Ruff, mypy, pytest), and the single lockfile `uv.lock`. Mining and evaluation depend on `invest-data` only for its public, versioned bundle contract (`invest_data.bundle` and `invest_data.schemas`). They never import each other.

## Getting started

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). The three packages form one uv workspace with a single committed lockfile; each package still installs on its own (CI checks this).

```sh
uv sync --frozen

# Whole workflow in one command (outputs under artifacts/synthetic-workflow):
uv run scripts/synthetic_workflow.sh
```

Or run the steps one by one. Each reads only the artifacts the previous one published; the script runs the same steps except the fundamentals diagnostic:

```sh
# 1. Prepare: publish a deterministic synthetic market (or `import-csv` your own bars).
uv run invest-data synthetic --out artifacts/data/synthetic --format parquet \
  --universe-out artifacts/data/universe --fundamentals-out artifacts/data/fundamentals

# 2. Mine: random search + templates on the development period, with a full trial
#    ledger; the top candidates are tested once on the confirmation period (Holm).
uv run invest-mine search --data artifacts/data/synthetic --universe artifacts/data/universe \
  --trials 200 --out artifacts/mining/search
uv run invest-mine evaluate --data artifacts/data/synthetic --fundamentals artifacts/data/fundamentals \
  --expr "cs_rank(fund_book_to_price)" --out artifacts/mining/value

# 3. Export the first development-selected factor from the first confirmation date.
uv run invest-mine export --data artifacts/data/synthetic --universe artifacts/data/universe \
  --from-search artifacts/mining/search --out artifacts/signals/best

# 4. Evaluate: backtest with costs, metrics, statistics, stress scenarios and figures.
#    The deflated Sharpe uses the search's proposal count recorded in the signals bundle.
uv run invest-eval run --data artifacts/data/synthetic --signals artifacts/signals/best \
  --universe artifacts/data/universe \
  --config strategy-evaluation/examples/quantile_long_short.json --out artifacts/eval/best
```

Checks (the same as CI):

```sh
uv run ruff format --check . && uv run ruff check .
uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src
uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch
uv run python scripts/check_markdown_links.py
```

CI additionally builds the three wheels and runs the tests against the installed packages; see the [CI/CD guidelines](CI_CD_GUIDELINES.md).

Automatic export follows the candidate order frozen during development. Confirmation scores and pass/reject outcomes never choose the replayed factor; inspect `confirmation.csv` separately. A portfolio replay does not promote a rejected or inconclusive factor. Changing `--rank` or strategy settings after inspecting confirmation results makes subsequent replays exploratory and requires new untouched data for final validation.

### Key conventions

- **Timing.** A signal dated `t` uses data through the close of `t`. Orders fill at the open of `t + 1 + delay`. Factor labels use the same convention (open `t+1` to open `t+1+h`), so mining diagnostics and backtests agree. Tests check that changing future prices or signals cannot change earlier signals, fills or equity.
- **Costs.** Commission and half-spread (bps of notional), plus square-root market impact `impact_coef × daily_vol × sqrt(notional / ADV$)`, a participation cap per fill, short borrow fees, and interest on cash. Volatility and ADV are trailing estimates known at the decision date. Stress scenarios scale costs, add delays, tighten participation, and raise capital.
- **Survivorship and universes.** Orders with no bar on the fill date are rejected. Missing later bars never imply a delisting: held instruments retain their last known mark, with a warning. Supply known cash settlement events through `invest-eval run --delistings <events.json>` to settle positions at the event date's close and supplied price. See the [event contract](strategy-evaluation/README.md#delisting-settlements). An optional universe bundle gives point-in-time membership: mining ranks only members, and the backtest opens positions only in members.
- **Fundamentals.** An optional fundamentals bundle records when each value (and each revision) was published. Expressions read them as `fund_<field>` with the value known at each date's close, never a later revision.
- **Storage.** Bundles are CSV, SQLite or Parquet, validated by one reader and identified by a format-independent content hash.
- **Undefined results.** Metrics carry a status and reason (for example `undefined: zero_excess_return_dispersion`) instead of returning 0 or infinity.
- **Insolvency.** Simulation stops when equity becomes nonpositive. Reports retain net loss and drawdown evidence, while growth and risk ratios carry explicit invalid-input statuses.
- **Statistics and diagnostics.** Sharpe confidence intervals, PSR, and DSR use the configured risk-free excess-return basis. Flat/no-trade portfolios produce undefined statistics and complete reports. Quantile membership uses decision-time signals before filtering unavailable future outcomes; an empty search family still produces a trial ledger and a structured confirmation table.

### Known limitations of the baseline

- There is no vendor download adapter yet. Use `import-csv` for your own bars (universe and fundamentals bundles can be published from DataFrames with `invest_data.schemas`), or add an adapter in `invest_data.sources`.
- Daily bars only. Fill prices are the open (mid) plus explicit costs; there is no intraday simulation, lot sizes or price limits. Target sizes use equity marked at the fill-date open.
- Missing marks can leave stale valuations until new prices or explicit settlements arrive. Historical claims require reliable settlement events and data-quality review; a final stored bar is not evidence of delisting. The baseline supports one cash settlement per instrument, on a market session, without separate settlement fees or relisting.
- Only external flows of zero are supported, so XIRR is not computed yet. Quantile-to-portfolio reports, regime splits and learned (fitted) models are still to do; see [TODO.md](TODO.md).

## Documentation maintenance

Update this README with changes to project status, supported capabilities, layout, prerequisites, and actual installation/execution/check commands. Keep detailed task progress in [TODO.md](TODO.md) and milestone acceptance in [ROADMAP.md](ROADMAP.md); update affected component READMEs in the same change. Mark work complete only with implementation and validation evidence. See the [maintenance checklist](TODO.md#updating-the-backlog-and-readme).

## Local files

The `.gitignore` excludes virtual environments, Python caches, build outputs, coverage reports, and local environment files. Keep credentials out of Git. A sanitized `.env.example` may be committed to document required configuration; dependency lockfiles should also be committed.
