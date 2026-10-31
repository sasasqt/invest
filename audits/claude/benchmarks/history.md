# Benchmark history: repo-audit-2026-10-31

- date: 2026-10-31
- main sha: 90b5ca038155b97833b120baa57dfecd05d6f641
- fingerprint: 7a47f774559b
- status: baseline
- window: 4
- skipped lines: 0
- tool version: 1.0.0

## Cases

| case | reps | wall s | cpu s | peak RSS MiB | output bytes | change wall | change cpu | change RSS | change bytes | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| formats-csv | 3 | 4.774 (4.720..4.776) | 5.614 (5.579..5.636) | 210.8 (210.7..210.8) | 6732462 (6732462..6732462) | - | - | - | - | - |
| formats-parquet | 3 | 5.048 (5.027..5.246) | 5.926 (5.889..6.142) | 245.9 (245.8..251.6) | 2857712 (2857712..2857712) | - | - | - | - | - |
| formats-sqlite | 3 | 4.502 (4.393..4.583) | 5.324 (5.181..5.426) | 195.6 (195.6..195.7) | 4643644 (4643644..4643644) | - | - | - | - | - |
| real-replay | 1 | 145.112 | 147.603 | 737.4 | 27628228 | - | - | - | - | insufficient-reps |
| synth-L | 3 | 50.997 (50.715..51.325) | 52.424 (52.234..52.833) | 465.0 (462.7..469.2) | 12355428 (12355428..12355428) | - | - | - | - | - |
| synth-M | 8 | 18.510 (18.056..19.054) | 19.951 (19.550..20.549) | 254.7 (251.6..257.5) | 3523734 (3523734..3523734) | - | - | - | - | - |
| synth-S | 8 | 6.770 (6.638..6.900) | 8.230 (8.117..8.374) | 179.7 (177.0..182.1) | 907727 (907727..907727) | - | - | - | - | - |
| synth-XL | 1 | 172.229 | 173.556 | 1325.5 | 41666957 | - | - | - | - | insufficient-reps |

## Stages (median seconds)

| case | stage | median s |
|---|---|---|
| formats-csv | invest-data synthetic | 1.921 |
| formats-csv | invest-mine export | 2.215 |
| formats-csv | invest-mine freeze | 0.599 |
| formats-parquet | invest-data synthetic | 2.004 |
| formats-parquet | invest-mine export | 2.501 |
| formats-parquet | invest-mine freeze | 0.624 |
| formats-sqlite | invest-data synthetic | 1.698 |
| formats-sqlite | invest-mine export | 2.164 |
| formats-sqlite | invest-mine freeze | 0.637 |
| real-replay | invest-data yahoo | 14.518 |
| real-replay | invest-eval quantiles | 69.462 |
| real-replay | invest-eval run | 32.775 |
| real-replay | invest-mine evaluate | 9.985 |
| real-replay | invest-mine export | 16.681 |
| real-replay | invest-mine freeze | 0.724 |
| real-replay | invest-mine ledger | 0.601 |
| synth-L | invest-data synthetic | 6.930 |
| synth-L | invest-eval quantiles | 16.094 |
| synth-L | invest-eval run | 9.929 |
| synth-L | invest-mine export | 5.891 |
| synth-L | invest-mine search | 12.135 |
| synth-M | invest-data synthetic | 2.059 |
| synth-M | invest-eval quantiles | 6.135 |
| synth-M | invest-eval run | 3.699 |
| synth-M | invest-mine export | 1.910 |
| synth-M | invest-mine search | 4.727 |
| synth-S | invest-data synthetic | 0.653 |
| synth-S | invest-eval quantiles | 2.236 |
| synth-S | invest-eval run | 1.934 |
| synth-S | invest-mine export | 0.829 |
| synth-S | invest-mine search | 1.095 |
| synth-XL | invest-data synthetic | 26.640 |
| synth-XL | invest-eval quantiles | 48.283 |
| synth-XL | invest-eval run | 31.537 |
| synth-XL | invest-mine export | 22.240 |
| synth-XL | invest-mine search | 43.525 |

## Scaling

- cases: synth-S, synth-M, synth-L, synth-XL
- b = 0.672

## Flags

- real-replay: insufficient-reps: 1 counted repetition(s)
- synth-XL: insufficient-reps: 1 counted repetition(s)

## Gate failures

- synth-S rep 2: output_hash 678772455aaa
- synth-S rep 3: output_hash 587b8f483f21
- synth-S rep 4: output_hash 7c21490e2a54
- synth-S rep 5: output_hash 54ee3fbc4bf9
- synth-S rep 6: output_hash 35a2fc032c32
- synth-S rep 7: output_hash 1285c4548b4b
- synth-M rep 2: output_hash 4e951f2ffdf3

## Failed repetitions

- synth-M rep 3: rc None

## Skipped lines

(none)
