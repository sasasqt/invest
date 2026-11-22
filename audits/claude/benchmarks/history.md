# Benchmark history: repo-audit-2026-11-22

- date: 2026-11-22
- main sha: eb64ad8f317fdb81d652a0c2ac1bbcbedd4b63f2
- fingerprint: fc1579baf121
- status: machine changed, not compared
- window: 4
- skipped lines: 0
- tool version: 1.0.0

## Cases

| case | reps | wall s | cpu s | peak RSS MiB | output bytes | change wall | change cpu | change RSS | change bytes | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| formats-csv | 3 | 20.749 (20.388..21.143) | 22.463 (22.057..22.793) | 232.2 (232.2..232.9) | 6682302 (6682302..6682302) | - | - | - | - | - |
| formats-parquet | 3 | 22.300 (22.159..22.747) | 24.043 (23.887..24.393) | 270.9 (265.5..272.2) | 3503075 (3503075..3503075) | - | - | - | - | - |
| formats-sqlite | 3 | 20.313 (20.255..21.088) | 21.913 (21.896..22.847) | 216.9 (216.8..216.9) | 4710840 (4710840..4710840) | - | - | - | - | - |
| real-replay | 1 | 211.430 | 213.531 | 758.9 | 27644738 | - | - | - | - | insufficient-reps |
| synth-L | 3 | 75.439 (72.742..77.161) | 76.576 (74.031..78.295) | 489.2 (487.7..489.5) | 12356503 (12356503..12356503) | - | - | - | - | - |
| synth-M | 7 | 25.545 (25.172..26.527) | 27.287 (26.752..28.042) | 271.4 (268.8..276.7) | 3525509 (3525509..3525509) | - | - | - | - | - |
| synth-S | 7 | 8.539 (8.357..8.898) | 10.356 (10.181..10.631) | 210.4 (209.1..211.8) | 913501 (913501..913501) | - | - | - | - | - |
| synth-XL | 1 | 276.336 | 276.344 | 1451.7 | 41658109 | - | - | - | - | insufficient-reps |

## Stages (median seconds)

| case | stage | median s |
|---|---|---|
| formats-csv | invest-data synthetic | 2.668 |
| formats-csv | invest-eval quantiles | 7.818 |
| formats-csv | invest-eval run | 4.868 |
| formats-csv | invest-mine export | 2.546 |
| formats-csv | invest-mine search | 2.833 |
| formats-parquet | invest-data synthetic | 2.887 |
| formats-parquet | invest-eval quantiles | 8.284 |
| formats-parquet | invest-eval run | 5.491 |
| formats-parquet | invest-mine export | 2.958 |
| formats-parquet | invest-mine search | 2.960 |
| formats-sqlite | invest-data synthetic | 2.603 |
| formats-sqlite | invest-eval quantiles | 7.706 |
| formats-sqlite | invest-eval run | 4.790 |
| formats-sqlite | invest-mine export | 2.332 |
| formats-sqlite | invest-mine search | 2.775 |
| real-replay | invest-data yahoo | 24.145 |
| real-replay | invest-eval quantiles | 94.814 |
| real-replay | invest-eval run | 46.457 |
| real-replay | invest-mine evaluate | 16.422 |
| real-replay | invest-mine export | 27.214 |
| real-replay | invest-mine freeze | 1.018 |
| real-replay | invest-mine ledger | 0.796 |
| synth-L | invest-data synthetic | 10.360 |
| synth-L | invest-eval quantiles | 21.410 |
| synth-L | invest-eval run | 14.504 |
| synth-L | invest-mine export | 9.950 |
| synth-L | invest-mine search | 18.815 |
| synth-M | invest-data synthetic | 2.909 |
| synth-M | invest-eval quantiles | 7.953 |
| synth-M | invest-eval run | 5.289 |
| synth-M | invest-mine export | 2.797 |
| synth-M | invest-mine search | 6.914 |
| synth-S | invest-data synthetic | 0.821 |
| synth-S | invest-eval quantiles | 2.801 |
| synth-S | invest-eval run | 2.552 |
| synth-S | invest-mine export | 1.038 |
| synth-S | invest-mine search | 1.358 |
| synth-XL | invest-data synthetic | 42.275 |
| synth-XL | invest-eval quantiles | 69.649 |
| synth-XL | invest-eval run | 53.834 |
| synth-XL | invest-mine export | 38.005 |
| synth-XL | invest-mine search | 72.568 |

## Scaling

- cases: synth-S, synth-M, synth-L, synth-XL
- b = 0.722

## Flags

- real-replay: insufficient-reps: 1 counted repetition(s)
- synth-XL: insufficient-reps: 1 counted repetition(s)

## Gate failures

(none)

## Failed repetitions

(none)

## Skipped lines

(none)
