# Invest

Invest is co-developed by human contributors, GPT, and Claude.

A modular Python investment research framework made of three independently installable components, each in its own top-level folder (`data-pipeline/data-preparation/`, `data-mining-framework/`, `strategy-evaluation/`). A first end-to-end baseline is implemented and tested: publish a dataset, mine and confirm factors, export frozen signals, and backtest them with explicit execution timing, costs, metrics, statistics, stress scenarios and figures. A test-only Yahoo Finance adapter runs the same workflow on historical prices from a saved raw snapshot (survivorship-biased; not research evidence). Portfolio reports show the factor's confirmation evidence and a rule-based portfolio verdict side by side, never merged. `invest-eval quantiles` backtests every signal decile and the top/bottom 1/5/10% tails as separate portfolios with the same costs, using the factor diagnostics' tie rule and reporting undersized buckets as `insufficient_data`. The next milestone is validation on that baseline and an authorized research data source. The agreed order of the remaining work is: null-simulation calibration and robustness perturbations (next), then shared contract fixtures, with code revisions in mining and data outputs (REPORT-03) and an authorized data source (SCOPE-01) alongside; see the [roadmap](ROADMAP.md) and [TODO.md](TODO.md). Development may use feature, experiment, or release branches as appropriate; the folder layout does not require all work to happen on `main`.

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

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). CI runs on Linux; Yahoo snapshot downloads do not work on Windows yet (see [Known limitations](#known-limitations-of-the-baseline)). The three packages form one uv workspace with a single committed lockfile; each package still installs on its own (CI checks this).

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
#    The confirmation-use ledger marks a rerun on the same period as exploratory.
uv run invest-mine search --data artifacts/data/synthetic --universe artifacts/data/universe \
  --trials 200 --ledger artifacts/mining/ledger.jsonl --out artifacts/mining/search
uv run invest-mine evaluate --data artifacts/data/synthetic --fundamentals artifacts/data/fundamentals \
  --expr "cs_rank(fund_book_to_price)" --out artifacts/mining/value

# 3. Export the first development-selected factor from the first confirmation date.
#    Its confirmation evidence (experiment, confirmation use, outcome) travels with the signals.
uv run invest-mine export --data artifacts/data/synthetic --universe artifacts/data/universe \
  --from-search artifacts/mining/search --out artifacts/signals/best

# 4. Evaluate: backtest with costs, metrics, statistics, stress scenarios and figures.
#    The deflated Sharpe uses the search's proposal count recorded in the signals bundle.
#    verdict.json and report.md show the factor and portfolio verdicts separately.
uv run invest-eval run --data artifacts/data/synthetic --signals artifacts/signals/best \
  --universe artifacts/data/universe \
  --config strategy-evaluation/examples/quantile_long_short.json --out artifacts/eval/best

# 5. Bucket portfolios: each decile and the top/bottom 1/5/10% tails as separate backtests.
uv run invest-eval quantiles --data artifacts/data/synthetic --signals artifacts/signals/best \
  --universe artifacts/data/universe \
  --config strategy-evaluation/examples/quantile_long_short.json --out artifacts/eval/quantiles
```

### Historical workflow (Yahoo Finance, test-only)

Needs network access to `query1.finance.yahoo.com` for the first run only:

```sh
uv run scripts/historical_workflow.sh   # outputs under artifacts/historical-workflow
```

It saves the raw Yahoo responses for today's S&P 100 members ([list](scripts/sp100_members.txt)) and SPY from 2010 to 2024 in `artifacts/historical-workflow/snapshot`, publishes the members and SPY as separate bundles, freezes the 5-day reversal formula `close / delay(close, 5) - 1` with orientation −1 and `n_trials = 1`, exports its signals, evaluates them with the example quantile long-short config, reporting SPY next to the universe equal-weight benchmark, and backtests every decile and top/bottom tail portfolio with the same config (`quantiles/report.md`).

Existing snapshots replay offline using their saved request dates by default. `START` and `END` select an inclusive subset within that request; requests beyond it fail before publication. Dataset ids and selection provenance use the resolved dates, while provenance retains the original download request. `SYMBOLS_FILE` controls new downloads only; replay uses the saved symbols and excludes `BENCHMARK` from the strategy universe. Override `BENCHMARK`, `SNAPSHOT` or `CONFIG` as needed. The same snapshot and selection publish identical dataset hashes. Yahoo publication currently supports USD US equities and ETFs only. External benchmarks must have matching currency, frequency, price adjustment, calendar and declared timezone; missing closes exclude incomplete daily intervals from relative metrics. Reports show benchmark identity and aligned observation counts, with an explicit insufficient-data reason when fewer than 20 daily returns align.

The committed [confirmation-use ledger](ledgers/yahoo-test.jsonl) records 2010-01-01 to 2024-12-31 as already inspected, so this history only gives exploratory evidence, and reserves 2025-01-01 onward, which has never been downloaded or inspected, for a future confirmation. The workflow checks `LEDGER` (default that file) and refuses any `START`/`END` reaching 2025 before downloading or publishing. See [confirmation-use ledger](#confirmation-use-ledger).

The result is **survivorship-biased**: names chosen today are applied to all history, delisted companies are missing, and Yahoo revises adjusted prices. Use it to check the workflow on real prices, not as alpha evidence. The first run (2026-10-06) is recorded with its data hashes in [the historical baseline](docs/HISTORICAL_BASELINE.md): the 5-day reversal had a gross Sharpe of 0.11 and lost 5.6% a year after costs. Its report shows the factor as `not_confirmed` and the portfolio as `inconclusive`. Fresh downloads on later code, most recently on 2026-10-07 with version 2 verdicts, reproduced every reported metric and both verdicts, though with new dataset hashes because Yahoo's responses had changed. An offline replay of that snapshot on the current code reproduced the saved metrics and verdicts exactly.

### Run records

The [saved outputs of the 2026-10-07 run](runs/yahoo-test/2026-10-07/README.md) (reports, verdicts, figures and manifests; no vendor data) are committed under `runs/`. To save a future run's record the same way, set `RECORD`, then commit that folder:

```sh
RECORD=runs/yahoo-test/<date> uv run scripts/historical_workflow.sh
```

[scripts/save_run.py](scripts/save_run.py) writes the record. It never overwrites or deletes an existing folder and copies no vendor data: it stages in a folder it creates itself, and refuses a destination that appears while it is saving, on Linux, macOS and Windows. It refuses an incomplete run: every workflow output, including the report, figures and the benchmark manifest when a benchmark was used, must exist. It also refuses a run whose evaluation or quantile-portfolio manifest does not show committed code. Records include the quantile report and portfolio table but not the per-decision membership and daily-return tables, which replay rebuilds. `invest-eval` records `code_revision` and `code_dirty` from the Git checkout its code was loaded from, not from the directory it was started in, and records `null` for both when Git does not track that code (for example an installed wheel). The workflow additionally checks for a clean checkout before it starts.

Checks (the same as CI):

```sh
uv run ruff format --check . && uv run ruff check .
uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src
uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch
uv run python scripts/check_markdown_links.py
```

CI additionally builds the three wheels and runs the tests against the installed packages; see the [CI/CD guidelines](CI_CD_GUIDELINES.md).

The offline Markdown check validates relative links and heading anchors, including literal underscores and duplicate-heading collisions, while ignoring links inside inline and fenced code examples.

### Confirmation-use ledger

A confirmation period gives confirmatory evidence only once. `invest-mine search --ledger <file>` records each search (experiment id from the dataset and input hashes, operator version, search settings and split) in an append-only JSON Lines ledger, one per market. Before any candidate is scored it classifies the run:

- **confirmatory**: the confirmation window overlaps no earlier search's development or confirmation window and no recorded inspection, and is not a repeat.
- **exploratory**: anything else. The run still completes, but `confirmation.csv` reports `status = exploratory` (the raw result stays in `test_outcome`), and `config.json` and the frozen factors record the experiment id, use and reasons. `--require-confirmatory` refuses instead.

The ledger's development window includes every price used by its forward-return labels, including dates in the decision purge gap. For horizon `h`, decision `t` needs prices through session `t+1+h`; that session must precede the first confirmation session and any embargo. Search configuration reports decision dates in `split.development` and the full observed range in `split.development_observations`. The ledger API validates entries before appending and rejects overrides of its version, kind and recording timestamp without changing the file.

`invest-mine ledger reserve|inspect|check --ledger <file> --start <date> [--end <date>]` reserves an untouched window, records one already looked at, or fails if a window touches an unused reservation. `invest-mine evaluate --ledger <file>` refuses reserved data and records its full-sample window. A search whose development data touches a reservation is refused; to use the reservation, confirm on it with `--confirm-start <first reserved date>`, which uses it up. A single formula fixed in advance with `invest-mine freeze` is confirmed the same way with `invest-mine confirm --factor <factor.json> --confirm-start <date> --ledger <file>`: a one-sided HAC test of its rank IC on the confirmation window, recorded as an experiment whose development window is only the formula's lookback history. A second confirmation of the same window is exploratory. Search-selected factors are refused, because confirming family members one at a time would undo the Holm adjustment. Without `--ledger`, search results say `confirmation_use = unrecorded`; `confirm` always requires a ledger. Backtests in `invest-eval` are not recorded automatically: record their windows with `ledger inspect`, as the historical workflow does through its check and diagnostics.

Zero-lookback fixed formulas, such as `close`, can confirm from the dataset's first session without historical inputs. Their ledger entries record `development: null` and `params.lookback_sessions: 0`; no unused session is treated as development. Formulas with a positive lookback still require preceding history, and all confirmations retain reservation and repeat-use checks.

Automatic export follows the candidate order frozen during development. Confirmation scores and pass/reject outcomes never choose the replayed factor; inspect `confirmation.csv` separately. A portfolio replay does not promote a rejected or inconclusive factor. Changing `--rank` or strategy settings after inspecting confirmation results makes subsequent replays exploratory and requires new untouched data for final validation.

### Factor and portfolio verdicts

After the factor is chosen, `invest-mine export` attaches its confirmation evidence to the signals bundle as `metadata.factor_evidence`: the experiment id, whether it came from a search or `confirm`, the confirmation use, the raw test outcome, the reported status (`exploratory` whenever the confirmation data had been used before), the tested horizon, the family size, the confirmation window and the test statistics. `--from-search` attaches the evidence from the same search output; for a frozen factor pass `--confirmation <search or confirm output>`. The export refuses evidence for a different factor, experiment or horizon and contradictory statuses. Evidence v2 binds the tested horizon to the signals; v1 evidence must be [re-exported from original confirmation results](docs/DATA_CONTRACT.md#signal-confirmation-evidence), without rerunning confirmation. The shared signals contract validates the evidence on publication and on read ([data contract](docs/DATA_CONTRACT.md)).

`invest-eval run` copies that evidence unchanged into `verdict.json` under `factor` (`not_confirmed` when the signals have none) and adds a separate `portfolio` verdict: `supported`, `rejected`, `inconclusive` or `insufficient_data`, from the rules declared in the config's `validation` section (minimum sessions, net Sharpe bootstrap interval, deflated Sharpe, named stress scenarios and an optional benchmark). Each rule is saved as a check with its value and threshold, and `report.md` shows the two verdicts in separate sections. Neither verdict changes the other: a supported portfolio does not confirm a factor, and a confirmed factor does not validate a portfolio. The portfolio verdict is about the evaluated window only; it is confirmatory only if that window was untouched, which the evaluator does not check (see [Known limitations](#known-limitations-of-the-baseline)).

### Decile and tail portfolios

`invest-eval quantiles` runs one backtest per bucket through the same engine, costs, timing and eligibility as `invest-eval run` (QUANTILE-01): long-only portfolios for each of `--buckets` (default 10) deciles, long-only top and bottom slices for each `--tails` fraction (default 1%, 5%, 10%), and a top-minus-bottom long-short portfolio per fraction. Membership is the factor diagnostics' rule applied to decision-time eligible names: average-rank percentile `p`, bucket `k` holds `ceil(p × n) = k`, top `f` holds `p > 1 − f`, bottom `f` holds `p ≤ f`, so tied scores always share a bucket. Tails overlap deciles and each other and are never summed. A leg with fewer than `--min-names-per-bucket` (default 5) names holds nothing on that decision, and the portfolio is reported as `insufficient_data` without performance figures; with about 100 names, the 1% tails always are. `quantiles.json` (`report_version = 1`) and `tables/portfolios.csv` give, per portfolio, net and gross CAGR and Sharpe, a bootstrap Sharpe interval, drawdown, turnover, cost drag, name counts and status; `tables/memberships.csv.gz` gives each decision's percentiles and buckets, and `report.md` and `figures/quantile_portfolios.png` are rendered from the saved files. These are portfolio results for the evaluated window only; they do not confirm the factor and get no verdict.

### Key conventions

- **Timing.** A signal dated `t` uses data through the close of `t`. Orders fill at the open of `t + 1 + delay`. Factor labels use the same convention (open `t+1` to open `t+1+h`), so mining diagnostics and backtests agree. Tests check that changing future prices or signals cannot change earlier signals, fills or equity.
- **Costs.** Commission and half-spread (bps of notional), plus square-root market impact `impact_coef × daily_vol × sqrt(notional / ADV$)`, a participation cap per fill, short borrow fees, and interest on cash. Volatility and ADV are trailing estimates known at the decision date. Stress scenarios scale costs, add delays, tighten participation, and raise capital.
- **Survivorship and universes.** Orders with no bar on the fill date are rejected. Missing later bars never imply a delisting: held instruments retain their last known mark, with a warning. Supply known cash settlement events through `invest-eval run --delistings <events.json>` to settle positions at the event date's close and supplied price. See the [event contract](strategy-evaluation/README.md#delisting-settlements). An optional universe bundle gives point-in-time membership: mining ranks only members, and the backtest opens positions only in members.
- **Fundamentals.** An optional fundamentals bundle records when each value (and each revision) was published. Expressions read them as `fund_<field>` with the value known at each date's close, never a later revision.
- **Storage.** Bundles are CSV, SQLite or Parquet, validated by one reader and identified by a format-independent content hash.
- **Undefined results.** Metrics carry a status and reason (for example `undefined: zero_excess_return_dispersion`) instead of returning 0 or infinity.
- **Insolvency.** Simulation stops when equity becomes nonpositive. Reports retain net loss and drawdown evidence, while growth and risk ratios carry explicit invalid-input statuses. Portfolio verdict v2 always rejects known insolvency, even with positive bootstrap/DSR statistics or disabled stress checks; a missing, undefined or invalid base net Sharpe cannot support a portfolio.
- **Statistics and diagnostics.** Sharpe confidence intervals, PSR, and DSR use the configured risk-free excess-return basis. Flat/no-trade portfolios produce undefined statistics and complete reports. Quantile membership uses decision-time signals before filtering unavailable future outcomes; factor tail slices with fewer than `invest-mine evaluate --min-tail-names` (default 5) names on any date report `insufficient_data` instead of a mean return. An empty search family still produces a trial ledger and a structured confirmation table.

### Known limitations of the baseline

- The only network adapter is the test-only Yahoo Finance one (`invest-data yahoo`); it has no delisted tickers, point-in-time membership or fundamentals. For research data use `import-csv` with your own bars (universe and fundamentals bundles can be published from DataFrames with `invest_data.schemas`), or add an adapter beside `invest_data.yahoo`.
- Yahoo snapshot downloads publish by renaming a staging directory onto an empty reserved directory, which works on Linux and macOS but fails on Windows. CI does not test Windows.
- Daily bars only. Fill prices are the open (mid) plus explicit costs; there is no intraday simulation, lot sizes or price limits. Target sizes use equity marked at the fill-date open.
- Missing marks can leave stale valuations until new prices or explicit settlements arrive. Historical claims require reliable settlement events and data-quality review; a final stored bar is not evidence of delisting. The baseline supports one cash settlement per instrument, on a market session, without separate settlement fees or relisting.
- Only external flows of zero are supported, so XIRR is not computed yet. The confirmation-use ledger compares windows by date within one ledger file, so keep one ledger per market and assume a single writer. The portfolio verdict does not consult the confirmation-use ledger, so a backtest on already inspected data still gets a verdict; read it as exploratory unless its window was untouched. Its rules are not yet calibrated by null simulations. Regime splits and learned (fitted) models are still to do; see [TODO.md](TODO.md).

## Documentation maintenance

Update this README with changes to project status, supported capabilities, layout, prerequisites, and actual installation/execution/check commands. Keep detailed task progress in [TODO.md](TODO.md) and milestone acceptance in [ROADMAP.md](ROADMAP.md); update affected component READMEs in the same change. Mark work complete only with implementation and validation evidence. See the [maintenance checklist](TODO.md#updating-the-backlog-and-readme).

## Local files

The `.gitignore` excludes virtual environments, Python caches, build outputs, coverage reports, and local environment files. Keep credentials out of Git. A sanitized `.env.example` may be committed to document required configuration; dependency lockfiles should also be committed.
