# Historical baseline (Yahoo Finance, test-only)

The first run of the documented workflow on real historical prices (FLOW-02). It checks that the pipeline works on representative data; it is **not** evidence of alpha, because the universe is survivorship-biased and the vendor revises adjusted history.

## How to reproduce

```sh
uv run scripts/historical_workflow.sh                       # first run: downloads the snapshot
SNAPSHOT=<saved snapshot> uv run scripts/historical_workflow.sh <new out dir>   # offline replay
```

See the [README](../README.md#historical-workflow-yahoo-finance-test-only) for what each step does. Republishing the same snapshot gives the same dataset hashes in any storage format (checked for CSV and Parquet below). A new download gives a new snapshot and, if Yahoo has revised its adjusted prices, different hashes.

Replay defaults to the saved request dates. `START`/`END` select a subset inside that range and produce new selection provenance and dataset ids; `SYMBOLS_FILE` is used only on download. Publication validates US equity/ETF source metadata, and benchmark comparison requires matching market metadata and complete daily intervals. The first table below is from the original run; the review fixes were then checked with a fresh download (see the section after the results).

## Run of 2026-10-06

| item | value |
|---|---|
| Universe | 101 S&P 100 members listed on 2026-10-06 ([list](../scripts/sp100_members.txt)), applied to all history; SNDK had no data in the period (HTTP 400, recorded in the snapshot) so 100 names were published |
| Period | sessions 2010-01-04 to 2024-12-31 (3,774); backtest 2010-01-11 to 2024-12-31 (3,769) |
| Snapshot | retrieved 2026-10-06T02:28:51Z; `snapshot.json` SHA-256 `738cfc38f0cd04ef2fde23ed5f90f3c2ae3cdc066c5bdf274aa3b22ba07d75f4` |
| Market bundle | 363,015 rows, 0 rejected; `content_sha256` `686133f9c6ff8a09b7af6f3f6cdf101033df28a5610ec569c193dc7b1a308e11` (Parquet and CSV) |
| Benchmark bundle | SPY, 3,774 rows; `content_sha256` `4c98173a59e8220625a17b6678bbc68348d2cb4a53ae7316288a35d671fa8294` |
| Signal | `close / delay(close, 5) - 1`, orientation −1, frozen a priori (`n_trials = 1`), factor `f_f4031d273d5d` |
| Strategy | [example config](../strategy-evaluation/examples/quantile_long_short.json): top/bottom 10% long-short, gross leverage 1, rebalance every 5 sessions, fill at next open, 1 bp commission, 5 bp half-spread, square-root impact 0.5, 50 bp/yr borrow |

### Factor diagnostics (full sample, descriptive)

Mean daily rank IC of the raw 5-day return against the next 5-day open-to-open return is −0.0113 (HAC t = −2.06, two-sided p = 0.039, 3,763 dates, about 96 names per date), so the reversal direction holds on average but is weak; ICIR is −0.056 and only 48% of dates have the expected sign.

### Portfolio results

| metric | net of costs | gross of costs |
|---|---|---|
| CAGR | −5.64% | 0.50% |
| Sharpe | −0.47 | 0.11 |
| Max drawdown | 61.8% | 20.6% |

- Costs: 5.9% a year of drag at about 44× one-way annual turnover; the gross edge does not cover them. Doubling costs gives a Sharpe of −1.01; a one-session delay gives −0.65.
- Statistics: Sharpe 95% stationary-bootstrap CI [−0.97, 0.03]; HAC t of the mean daily return −1.80 (p = 0.072); PSR/DSR versus zero 0.036.
- Benchmarks: the universe equal-weight portfolio (gross) returned 1,210% and SPY returned 574% over the same sessions. Against SPY the strategy has beta 0.11, correlation 0.17, annual alpha −6.8% and information ratio −1.04.

An offline replay of the same snapshot from the clean committed revision `5082f63` reproduced every dataset hash and every metric exactly.

### Fresh download on the reviewed code (2026-10-06)

A new download about ten hours later, run with `scripts/historical_workflow.sh` on main at `d750df0` (after the review fixes), again published 100 names and 363,015 market rows with no rejections, and SNDK again failed with HTTP 400. Its dataset hashes differ from the first run (`content_sha256` `bff5755f00fac78ffacfb81f5781020fb3f98b19572356b031badaab2ccfd6f3` for the market, `23b484a789caf3dfc3b65d44a4ebd2ccf735ff19e73a3bed37dbffb88558e02d` for SPY), so Yahoo's responses changed between downloads: the parsing, adjustment, cleaning and bundle code is unchanged since `5082f63` apart from a date filter that dropped no rows. Republishing the new snapshot as CSV and Parquet gave identical hashes. Every reported metric above matched to the shown precision (net CAGR −5.64%, net Sharpe −0.47, gross Sharpe 0.11, max drawdown 61.8%, equal-weight 1,210%, SPY 574%, information ratio vs SPY −1.04, DSR 0.036). This shows why the snapshot, not the vendor, must define the dataset. The review fixes changed no reported number, but because the data also changed this is not a like-for-like replay of the original snapshot. Offline replays with `START`/`END` inside the saved range ran, and a range beyond it was refused before publication.

### Verdicts on the current code (2026-10-07)

A fresh download on this branch reproduced the metrics above to the shown precision (net CAGR −5.64%, net Sharpe −0.47; market `content_sha256` `a003581dd36cbf7f26220cb4f2047c2a20165eff1c2777fc8a42028742330222`). Its report now shows the two verdicts separately. Factor: `not_confirmed`, because the fixed formula has not been confirmed (the 2025+ window stays reserved). Portfolio: `inconclusive` under the example config's rules: the Sharpe interval [−0.97, 0.03] includes zero, so it is not `rejected`, while the deflated Sharpe (0.036), `costs_x2` (−1.01) and `delay_1` (−0.65) checks fail. Because 2010–2024 was already inspected, this verdict is exploratory.

Another fresh download on 2026-10-07 (retrieved 10:32 UTC), on main at `4e439f0` after the version 2 verdict and evidence changes, again published 100 names and 363,015 market rows with no rejections (SNDK again HTTP 400; market `content_sha256` `1fc2a8037ffe0674986adf07491ef6f89df765b135c10e94bec68edaff441129`, SPY `02cd765d1fb1b02cfa24587d07fd2dc7083caee3d8fa2c865f7b3b5878b7cf6c`). Every metric above matched to the shown precision and both verdicts were unchanged. The new mandatory checks passed: the wealth path stayed solvent and the base net Sharpe (−0.47) was valid, so the portfolio stays `inconclusive` for the reasons above. The run used a temporary copy of the ledger, so the committed ledger is unchanged. An offline replay of that snapshot on a clean checkout of `c6f2961` published the same hashes and results; its reports, metrics, verdicts, figures and manifests are saved in [runs/yahoo-test/2026-10-07](../runs/yahoo-test/2026-10-07/README.md). A later offline replay of the same snapshot on main at `6b2ed6e` (after the run-record fixes) gave identical metrics and verdicts and recorded that revision with `code_dirty = false`.

**Conclusion:** the workflow runs end to end on real prices with recorded data identity. The fixed 5-day reversal rule loses money after realistic costs on this universe, and the equal-weight benchmark's return is inflated by survivorship bias.

## Confirmation use

Historical mining diagnostics saved before the PR #16 review fixes used the raw reversal expression (orientation +1). New workflow diagnostics use the frozen orientation -1, matching the exported scores and executable bucket labels. IC signs and diagnostic bucket direction therefore differ from those older mining reports; the baseline portfolio signals, metrics and verdict are unchanged.

Both runs requested 2010-01-01 to 2024-12-31 and inspected all of it (full-sample diagnostics and the backtest), so this history can only give exploratory evidence. Data from 2025-01-01 onward has never been downloaded or inspected. [`ledgers/yahoo-test.jsonl`](../ledgers/yahoo-test.jsonl) records both facts, and the workflow refuses to download or publish any window reaching 2025. A future confirmatory test must freeze its candidates on 2010–2024 and confirm once on 2025 onward: a search family with `invest-mine search --data <market bundle> --ledger ledgers/yahoo-test.jsonl --confirm-start 2025-01-01 --out <dir>`, or the fixed 5-day reversal with `invest-mine confirm --data <market bundle> --factor <factor.json> --ledger ledgers/yahoo-test.jsonl --confirm-start 2025-01-01 --out <dir>`. The historical workflow refuses that window, so download and publish a snapshot reaching past 2025 with `invest-data yahoo download|publish` directly, and run nothing else on the reserved dates before confirming.

## Limitations

- Eligibility look-ahead: the example config's `min_price = 1.0` compares back-adjusted closes, so splits and dividends after a date decide which names were eligible on it (REVIEW-13). On this snapshot NVDA was ineligible until 2016. The results above include this effect and will change when it is fixed.
- Survivorship bias: only companies that are S&P 100 members today; failed and removed companies are missing, and late listings (for example META, ABBV, UBER, PLTR) enter when their history starts.
- Yahoo adjusted prices are revised after each dividend and split; the snapshot, not the vendor, defines the data. Total-return adjustment scales open/high/low/close by `adjclose / close`.
- No point-in-time membership, fundamentals, delisting events or borrow availability.
