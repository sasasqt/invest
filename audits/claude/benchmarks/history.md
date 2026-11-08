# Benchmark history: repo-audit-2026-11-08

- date: 2026-11-08
- main sha: 9913f94b9b795bd9633a6a683e9f420301e400b3
- fingerprint: 8766a82088ae
- status: machine changed, not compared
- window: 4
- skipped lines: 0
- tool version: 1.0.0

## Cases

| case | reps | wall s | cpu s | peak RSS MiB | output bytes | change wall | change cpu | change RSS | change bytes | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| formats-csv | 3 | 3.656 (3.538..3.723) | 4.394 (4.284..4.479) | 213.4 (213.2..213.7) | 5161279 (5161279..5161279) | - | - | - | - | - |
| formats-parquet | 3 | 3.742 (3.695..3.818) | 4.490 (4.444..4.562) | 251.1 (248.8..252.9) | 2453692 (2453692..2453692) | - | - | - | - | - |
| formats-sqlite | 3 | 3.457 (3.335..3.493) | 4.189 (4.082..4.223) | 198.2 (198.1..198.3) | 3271578 (3271578..3271578) | - | - | - | - | - |
| real-replay | 1 | 130.551 | 133.698 | 738.0 | 27640100 | - | - | - | - | insufficient-reps |
| synth-L | 3 | 54.589 (53.654..56.367) | 56.344 (55.447..58.087) | 469.5 (468.7..470.4) | 12354835 (12354835..12354835) | - | - | - | - | - |
| synth-M | 7 | 21.087 (20.431..21.217) | 22.748 (22.235..23.009) | 256.3 (248.8..257.0) | 3522115 (3522115..3522115) | - | - | - | - | - |
| synth-S | 7 | 7.700 (7.625..7.865) | 9.527 (9.470..9.706) | 180.8 (180.4..183.5) | 907883 (907883..907883) | - | - | - | - | - |
| synth-XL | 1 | 164.181 | 165.772 | 1336.0 | 41656041 | - | - | - | - | insufficient-reps |

## Scaling

- cases: synth-S, synth-M, synth-L, synth-XL
- b = 0.637

## Flags

- real-replay: insufficient-reps: 1 counted repetition(s)
- synth-XL: insufficient-reps: 1 counted repetition(s)

## Gate failures

(none)

## Failed repetitions

(none)

## Skipped lines

(none)
