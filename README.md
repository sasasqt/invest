# Invest

A modular Python investment research framework made of three independently installable components in two top-level folders. A first end-to-end baseline is implemented and tested: publish a dataset, mine and confirm factors, export frozen signals, and backtest them with explicit execution timing, costs, metrics, statistics, stress scenarios and figures. Development may use feature, experiment, or release branches as appropriate; the folder layout does not require all work to happen on `main`.

## Components

- [Data preparation](data-pipeline/data-preparation/README.md): download, clean, preprocess, and publish CSV or SQLite datasets.
- [Strategy evaluation](data-pipeline/strategy-evaluation/README.md): apply trading rules to supplied data/signals and evaluate portfolio performance after costs.
- [Data mining framework](data-mining-framework/README.md): consume published datasets for factor discovery, model training, inference, and signal diagnostics.

The components exchange artifacts through a [versioned dataset contract](docs/DATA_CONTRACT.md). They do not depend on each other's private implementation; any shared public contract/runtime utility must have an explicit versioned interface. Each component will contain its own Python package, dependency configuration, and tests. See the [architecture guide](docs/ARCHITECTURE.md) for the folder layout and ownership boundaries.

## Development guidelines

Read [Python Development Guidelines](PYTHON_GUIDELINES.md) for the recommended project structure, extensibility practices, dependency management, coding standards, and testing workflow.

Read [Git Development Guidelines](GIT_GUIDELINES.md) for branch naming, focused commits, pull requests, history management, conflict resolution, and safe collaboration.

Read [Design by Contract Guidelines](DESIGN_BY_CONTRACT.md) for preconditions, postconditions, invariants, failure guarantees, boundary validation, numerical contracts, and interchangeable implementation tests.

Read [Rapid Software Development Guidelines](RAPID_DEVELOPMENT.md) for small working increments, bounded experiments, fast feedback, proportionate validation, technical debt management, and reliable research iteration.

The shared [quantile analysis](docs/QUANTILE_ANALYSIS.md) and [reporting](docs/REPORTING.md) specifications cover bucket comparisons, visualization ownership, and generated artifacts. The architecture guide lists the prerequisites for the first runnable end-to-end workflow.

Each component folder has a `src` package layout, its own `pyproject.toml`, and pytest tests under `tests/`. The root `pyproject.toml` defines the uv workspace, the shared dev tools (Ruff, mypy, pytest), and the single lockfile `uv.lock`. Mining and evaluation depend on `invest-data` only for its public, versioned bundle contract (`invest_data.bundle` and `invest_data.schemas`). They never import each other.

## Getting started

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). The three packages form one uv workspace with a single committed lockfile; each package still installs on its own (CI checks this).

```sh
uv sync --frozen

# 1. Prepare: publish a deterministic synthetic market (or `import-csv` your own bars).
uv run invest-data synthetic --out artifacts/data/synthetic

# 2. Mine: random search + templates on the development period, with a full trial
#    ledger; the top candidates are tested once on the confirmation period (Holm).
uv run invest-mine search --data artifacts/data/synthetic --trials 200 --out artifacts/mining/search
uv run invest-mine evaluate --data artifacts/data/synthetic --expr "-delta(close, 5)" --out artifacts/mining/rev5

# 3. Freeze and export signals for the confirmation period only.
uv run invest-mine export --data artifacts/data/synthetic \
  --factor artifacts/mining/search/factors/<factor_id>.json \
  --start <first confirmation date from search/config.json> --out artifacts/signals/rev5

# 4. Evaluate: backtest with costs, metrics, statistics, stress scenarios and figures.
uv run invest-eval run --data artifacts/data/synthetic --signals artifacts/signals/rev5 \
  --config data-pipeline/strategy-evaluation/examples/quantile_long_short.json \
  --n-trials 207 --out artifacts/eval/rev5
```

Checks (the same as CI):

```sh
uv run ruff format --check . && uv run ruff check .
uv run mypy data-pipeline/data-preparation/src data-mining-framework/src data-pipeline/strategy-evaluation/src
uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch
```

### Key conventions

- **Timing.** A signal dated `t` uses data through the close of `t`. Orders fill at the open of `t + 1 + delay`. Factor labels use the same convention (open `t+1` to open `t+1+h`), so mining diagnostics and backtests agree. Tests check that changing future prices or signals cannot change earlier signals, fills or equity.
- **Costs.** Commission and half-spread (bps of notional), plus square-root market impact `impact_coef × daily_vol × sqrt(notional / ADV$)`, a participation cap per fill, short borrow fees, and interest on cash. Volatility and ADV are trailing estimates known at the decision date. Stress scenarios scale costs, add delays, tighten participation, and raise capital.
- **Survivorship.** Instruments list and delist point-in-time. A held instrument that delists is liquidated at its final close (a delisting return of zero), and orders for instruments with no bar on the fill date are rejected and reported.
- **Undefined results.** Metrics carry a status and reason (for example `undefined: zero_excess_return_dispersion`) instead of returning 0 or infinity.

### Known limitations of the baseline

- There is no vendor download adapter yet. Use `import-csv` for your own bars or add an adapter in `invest_data.sources`.
- Daily bars only. Fill prices are the open (mid) plus explicit costs; there is no intraday simulation, lot sizes or price limits. Target sizes use equity marked at the fill-date open.
- Only external flows of zero are supported, so XIRR is not computed yet. Quantile-to-portfolio reports, regime splits and learned (fitted) models are still to do; see [TODO.md](TODO.md).

## Documentation maintenance

Update this README with changes to project status, supported capabilities, layout, prerequisites, and actual installation/execution/check commands. Keep detailed task progress in [TODO.md](TODO.md) and milestone acceptance in [ROADMAP.md](ROADMAP.md); update affected component READMEs in the same change. Mark work complete only with implementation and validation evidence. See the [maintenance checklist](TODO.md#updating-the-backlog-and-readme).

## Local files

The `.gitignore` excludes virtual environments, Python caches, build outputs, coverage reports, and local environment files. Keep credentials out of Git. A sanitized `.env.example` may be committed to document required configuration; dependency lockfiles should also be committed.
