# Benchmark history: repo-audit-2026-11-01

- date: 2026-11-01
- main sha: 90b5ca038155b97833b120baa57dfecd05d6f641
- fingerprint: 56c382251c65
- status: baseline
- window: 4
- skipped lines: 0
- tool version: 1.0.0

## Cases

| case | reps | wall s | cpu s | peak RSS MiB | output bytes | change wall | change cpu | change RSS | change bytes | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| formats-csv | 3 | 5.052 (5.009..5.249) | 5.742 (5.716..5.906) | 218.7 (218.6..219.3) | 5161548 (5161548..5161548) | - | - | - | - | - |
| formats-parquet | 3 | 5.638 (5.215..6.376) | 6.356 (5.973..7.099) | 254.4 (251.5..260.5) | 2453961 (2453961..2453961) | - | - | - | - | - |
| formats-sqlite | 3 | 4.589 (4.589..4.810) | 5.286 (5.265..5.489) | 203.5 (203.2..203.9) | 3271847 (3271847..3271847) | - | - | - | - | - |
| real-replay | 1 | 184.217 | 186.072 | 741.9 | 27628228 | - | - | - | - | insufficient-reps |
| synth-L | 3 | 66.165 (65.813..66.603) | 67.368 (67.223..68.037) | 474.4 (473.1..475.6) | 12355406 (12355406..12355406) | - | - | - | - | - |
| synth-M | 7 | 24.992 (23.975..26.301) | 26.745 (25.746..27.963) | 258.4 (252.7..264.0) | 3523712 (3523712..3523712) | - | - | - | - | - |
| synth-S | 7 | 9.213 (8.902..9.591) | 10.978 (10.716..11.410) | 186.7 (186.4..189.0) | 907705 (907705..907705) | - | - | - | - | - |
| synth-XL | 1 | 219.228 | 219.732 | 1327.5 | 41666935 | - | - | - | - | insufficient-reps |

## Stages (median seconds)

| case | stage | median s |
|---|---|---|
| formats-csv | invest-data synthetic | 2.359 |
| formats-csv | invest-mine search | 2.709 |
| formats-parquet | invest-data synthetic | 2.641 |
| formats-parquet | invest-mine search | 2.937 |
| formats-sqlite | invest-data synthetic | 2.095 |
| formats-sqlite | invest-mine search | 2.552 |
| real-replay | invest-data yahoo | 17.294 |
| real-replay | invest-eval quantiles | 93.209 |
| real-replay | invest-eval run | 39.869 |
| real-replay | invest-mine evaluate | 12.579 |
| real-replay | invest-mine export | 19.098 |
| real-replay | invest-mine freeze | 0.815 |
| real-replay | invest-mine ledger | 0.810 |
| synth-L | invest-data synthetic | 8.550 |
| synth-L | invest-eval quantiles | 21.332 |
| synth-L | invest-eval run | 12.133 |
| synth-L | invest-mine export | 7.126 |
| synth-L | invest-mine search | 16.347 |
| synth-M | invest-data synthetic | 2.522 |
| synth-M | invest-eval quantiles | 8.335 |
| synth-M | invest-eval run | 5.021 |
| synth-M | invest-mine export | 2.321 |
| synth-M | invest-mine search | 6.502 |
| synth-S | invest-data synthetic | 0.880 |
| synth-S | invest-eval quantiles | 3.061 |
| synth-S | invest-eval run | 2.579 |
| synth-S | invest-mine export | 1.132 |
| synth-S | invest-mine search | 1.506 |
| synth-XL | invest-data synthetic | 33.944 |
| synth-XL | invest-eval quantiles | 62.733 |
| synth-XL | invest-eval run | 39.092 |
| synth-XL | invest-mine export | 26.704 |
| synth-XL | invest-mine search | 56.749 |

## Scaling

- cases: synth-S, synth-M, synth-L, synth-XL
- b = 0.657

## Flags

- real-replay: insufficient-reps: 1 counted repetition(s)
- synth-XL: insufficient-reps: 1 counted repetition(s)

## Gate failures

(none)

## Failed repetitions

(none)

## Skipped lines

(none)
