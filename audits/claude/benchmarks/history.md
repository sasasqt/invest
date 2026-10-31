# Benchmark history: repo-audit-2026-10-31-2

- date: 2026-10-31
- main sha: 90b5ca038155b97833b120baa57dfecd05d6f641
- fingerprint: 7a47f774559b
- status: compared with 1 earlier run(s) on the same machine: repo-audit-2026-10-31
- window: 4
- skipped lines: 0
- tool version: 1.0.0

## Cases

| case | reps | wall s | cpu s | peak RSS MiB | output bytes | change wall | change cpu | change RSS | change bytes | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| synth-M | 3 | 18.209 (18.079..18.488) | 19.727 (19.599..20.051) | 259.9 (259.2..261.9) | 3523737 (3523737..3523737) | -1.6% | -1.1% | +2.0% | +0.0% | - |
| synth-S | 3 | 6.778 (6.716..6.879) | 8.255 (8.158..8.353) | 186.5 (185.3..188.3) | 907730 (907730..907730) | +0.1% | +0.3% | +3.8% | +0.0% | - |

## Stages (median seconds)

| case | stage | median s |
|---|---|---|
| synth-M | invest-data synthetic | 1.979 |
| synth-M | invest-eval quantiles | 6.111 |
| synth-M | invest-eval run | 3.644 |
| synth-M | invest-mine export | 1.977 |
| synth-M | invest-mine search | 4.633 |
| synth-S | invest-data synthetic | 0.666 |
| synth-S | invest-eval quantiles | 2.189 |
| synth-S | invest-eval run | 1.929 |
| synth-S | invest-mine export | 0.856 |
| synth-S | invest-mine search | 1.126 |

## Scaling

- cases: synth-S, synth-M, synth-L, synth-XL
- b: null (2 of the scaling cases have instrument_days and a median wall; at least 3 are needed)

## Flags

(none)

## Gate failures

(none)

## Failed repetitions

(none)

## Skipped lines

(none)
