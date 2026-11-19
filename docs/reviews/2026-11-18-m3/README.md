# Evidence for the 2026-11-18 checkpoint review

The scripts and outputs behind the numbers in the [checkpoint report](../2026-11-18-m3.md), pinned to `main` at `eb64ad8` (tag `checkpoint-m3-1`). Most were written and first run by the three reviewer sessions (R1 hand-offs, R2 statistics, R3 test health). The checkpoint session reran the ones marked *repeated* on a clean checkout of `eb64ad8`. Everything else is reviewer-reported. All runs used synthetic data or the saved 2026-10-07 Yahoo snapshot, and nothing touched the reserved 2025+ window or the tracked ledger.

The scripts are kept as they ran, with two changes: absolute paths are now environment variables, and the files are formatted and linted with ruff (a file-level `noqa` covers long lines). Set `INVEST` to a checkout of `eb64ad8` with `uv sync --frozen` done, and set `OUT` to an empty scratch folder. Run Python scripts with `$INVEST/.venv/bin/python`. Outputs named `*.reviewer.out` or kept under `out/` are the reviewer's. Outputs named `*.repeat*` or kept under `out/repeat/` are the checkpoint session's.

Not committed: the Yahoo snapshot and any output that prints its rows (vendor terms), and the bug-hunt findings ledger behind the escapes log, which by the project's rule stays outside the repository; its open rows are mirrored in [docs/audits/open-bugs.md](../../audits/open-bugs.md).

## REVIEW-57: size of the factor confirmation test ([hac/](hac/))

| Script | What it does | Seed, replications | Result |
|---|---|---|---|
| `null_hac_ma.py [reps] [seed]` | Feeds MA(h−1) IC series with mean 0 (what `h`-day overlapping labels give a persistent factor) to `newey_west_mean_test` with `newey_west_lags(n, h)`, the call `search.confirm` makes, and counts one-sided 5% rejections for n ∈ {60, 250, 750} and h ∈ {1, 5, 10, 20}. Also prints the share of the true long-run variance Bartlett weights at lag `h` capture (0.733 at h = 5, 0.683 at h = 20). | Seed 5, 4,000 (reviewer). *Repeated:* seed 5, 4,000 (identical output) and seed 6, 4,000. | n = 60: 0.105 (h = 5), 0.203 (h = 20). n = 250: 0.081, 0.119. Seed 6: 0.105, 0.201; 0.084, 0.115. Nominal 0.050; standard error 0.004 to 0.006 at these rates. Negative control: h = 1 with n = 750 gives 0.050 and 0.052. |
| `null_hac.py [reps] [sessions] [seed]` | The same test on the real pipeline: random-walk opens for 60 names, a factor independent of returns that is AR(1) over time (ρ = 0 or 0.98), `forward_returns`, Spearman `daily_ic`, 300 sessions. | Seed 2026, 400 (reviewer). *Repeated:* seed 7, 2,000. | Persistent factor (ρ = 0.98): 0.072 (h = 5) and 0.120 (h = 20) at 400 replications, standard error about 0.013 and 0.016. *Repeat:* 0.088 and 0.114 at 2,000, standard error about 0.006 and 0.007. Negative control: h = 1 gives 0.062 and 0.051. With ρ = 0 the IC series is barely autocorrelated, and the rate is 0.051 to 0.059 in the repeat. |
| `fix_direction.py` | Checks whether a longer Bartlett lag alone fixes the size. | Reviewer only. | A lag of 2h or 3h still gives 0.068 at n = 250 and h = 5, and 0.083 or 0.080 at n = 750 and h = 20, so the fix needs other kernel weights with matching critical values, or calibration. |

The ChatGPT review of #61 derived the same variance shares (0.7333 and 0.6833) independently.

## REVIEW-58 to REVIEW-61: hand-offs ([handoffs/](handoffs/))

The R1 scripts expect two synthetic markets and a search under `$OUT/work`:

```sh
B=$INVEST/.venv/bin W=$OUT/work
$B/invest-data synthetic --seed 7 --out $W/syn7 --universe-out $W/uni7 --fundamentals-out $W/fund7
$B/invest-data synthetic --seed 8 --out $W/syn8 --universe-out $W/uni8 --fundamentals-out $W/fund8
$B/invest-mine search --data $W/syn7 --universe $W/uni7 --trials 200 --ledger $W/ledger.jsonl --out $W/search7
$B/invest-mine export --data $W/syn7 --universe $W/uni7 --from-search $W/search7 --out $W/sig7
```

| Script | Finding | Expected if correct | Observed |
|---|---|---|---|
| `r1_import_frequency.sh` | REVIEW-59 (R1-1) | `import-csv` refuses weekly or Saturday-dated bars, or declares their real spacing | Both publish as `frequency: "1d"`, calendar `XNYS`; the weekly bundle evaluates with exit 0, annualised at 252. *Repeated* (`out/repeat/r1-1.txt`). |
| `weekly/make_weekly.py`, `weekly/eval_weekly.py` (R3) | REVIEW-59 (R3-1) | A weekly bundle is refused, or its metrics are annualised weekly | CAGR 16.1% and Sharpe 0.66 with status `ok`, where about 3.1% and 0.30 are right for weekly bars (`weekly/RESULT.txt`). Reviewer-reported. |
| `r1_declared_timing_metadata.py <out dir>` | REVIEW-59 (R1-4) | A universe declared with an inclusive end, or fundamentals declared known at the next open, are refused or read as declared | Both are read with the contract's own convention: the member drops one session early, and the value is used at the close one session early. Signals with another `available_at` are refused (the control). *Repeated* (`out/repeat/r1-4.txt`). |
| `r1_signals_market_and_horizon.sh` | REVIEW-58 (R1-2), REVIEW-60 (R1-3) | Evaluation refuses, or at least warns about, signals scored on another market, and shows the factor's horizon beside the holding period | Signals scored on seed 7 and evaluated on seed 8 exit 0 with no warning and `confirmation_passed`; the manifest records no market identity for the signals; horizon 1 against `rebalance_every` 5, and `report.md` never mentions the horizon. *Repeated* (`out/repeat/r1-2_3.txt`). |
| `r1_timing_parity.py <market>` | Label convention (checked, consistent) | The engine's holding return for one decision equals the mining label when `rebalance_every = h` and `delay = 0` | Equal to 1e-12. |
| `r1_bucket_rule_parity.py` | Bucket and tail rules (checked, consistent) | Mining and evaluation assign the same members | 0 mismatches in 377 cases with heavy ties. |
| `r1_scale_invariance_probe.py <market>` | Price-level scale check (checked) | No formula the check accepts changes under an earlier rescale | 421 accepted formulas; the only changes are rounding residue on flat windows, already REVIEW-47 and REVIEW-48. |
| `r1_trade_blotter_units.py <eval dir> <snapshot>` | REVIEW-61 (R1-5) | `trades.csv` says its units are adjusted, or shows as-traded values | Adjusted units without a statement. The output prints vendor-derived prices, so it is not committed. |
| `yahoo_split_check.py <snapshot>` | Yahoo split and volume adjustment (checked) | `close × volume` unchanged by the adjustment | Largest relative difference 2.2e-16. The output prints snapshot rows, so it is not committed. |
| `ntrials_lowered.sh` | K8 remainder (known, documented) | Without search evidence an explicit `--n-trials` replaces the bundle's count | It does, and it can turn a verdict into `supported`; with search evidence the lower value is refused. |
| `recheck_bh_2026_10_21_2.py <market>` | BH-2026-10-21-2 (fixed by #58) | A member settled at 0 counts −100% in the universe benchmark | It does. |

## Research validity ([research/](research/))

| Script | Check | Result (reviewer-reported) |
|---|---|---|
| `perturb/make_perturbed.py`, `perturb/run_cli.sh`, `perturb/compare.py` | Changing prices, volume, bars, universe intervals and fundamentals strictly after a date leaves every output at or before it unchanged, through the command-line tools on synthetic data | `perturb/compare.out`: every compared row is the same. |
| `yahoo/make_yahoo.py`, `yahoo/run_cli_y.sh`, `yahoo/compare_y.py` | The same on the Yahoo replay (Y1), and a later corporate action that rescales earlier prices (Y2) | `yahoo/compare_y.out`: Y1 the same exactly, Y2 the same up to rounding. |
| `ledger/ledger_paths.sh` | Reserved-window and reuse paths through the command-line tools, on a ledger copy | `ledger/ledger_paths.out`. |
| `stats_check.py` | PSR, DSR, the expected maximum Sharpe, both HAC implementations, Holm, Benjamini-Hochberg, rank IC with ties and the bootstrap block length against the published formulas | `stats_check.out`; the 2014 DSR paper's example gives 0.9004. |
| `null_verdict_stats.py` | Null size of the bootstrap Sharpe interval and PSR on independent returns | `null_verdict_stats.out`: within their nominal rates. |
| `known_recheck.py` | Known findings BH-2026-11-18-2 and BH-2026-11-18-3 | They reproduce. |

## REVIEW-62 to REVIEW-64: mutation sample ([mutation/](mutation/))

`mutants.py`, `mutants2.py` and `mutants3.py` define each mutant as an exact edit (file, original text, replacement), the test named for the behavior, and a wider test set to try when the named test passes. `run_mutants*.py` apply one mutant at a time to a throwaway copy of the checkout, run the named test with `pytest -x`, run the wider set if it survives, and restore the file. Run them with `MUTATION_REPO=<copy of eb64ad8>`, `INVEST` and `MUTATION_OUT` set. `results*_all.json` hold the reviewer's outcomes, one record per mutant with the tail of each pytest run.

Mutants M1 to M18, M21, M22, M23 and M25 make 22 distinct one-line changes. In batch 3, M1e, M3q, M3p and M2p rerun M1, M3 and M2 against other tests: `tests/test_pipeline.py`, the quantile causality test and `causality_variant_probe.py`, the release-gate causality test with `rebalance_every` 1 as well as 5.

- The named test kills 14 of the 22. The whole suite kills 20.
- M16 (no missing-mark warning) and M17 (a no-op `capital_x10`) survive the whole suite: REVIEW-64.
- M1e (`min_price` on the adjusted close) and M25 (no price-level scale check) survive `tests/test_pipeline.py`, which unit tests catch: REVIEW-62.
- M3 (scores one session ahead) survives the release-gate causality test at `rebalance_every` 5 and fails it at 1. M2 (liquidity one session ahead) survives both: REVIEW-63.
- `stale_mark_warning.py` shows the warning exists on the checkout, so M16's survival is a missing test, not missing code.

*Repeated:* the checkpoint session reran all three batches on a clean copy of `eb64ad8` on 2026-11-19 (`repeat/`). All 26 outcomes matched the reviewer's. It also ran the test trees outside M16's and M17's wider set (the data and mining tests, `tests/test_quantile_consistency.py` and `tests/test_check_coverage_floors.py`) with each mutant applied, and both passed. So the two survive every test that imports the evaluation package.
