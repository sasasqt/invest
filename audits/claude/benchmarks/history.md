# Benchmark history: repo-audit-2026-11-15

- date: 2026-11-15
- main sha: 2edd7ae1168eda1192ff73698ba5d42a7c034a41
- fingerprint: 0fa016b96104
- status: machine changed, not compared
- window: 4
- skipped lines: 0
- tool version: 1.0.0

## Cases

| case | reps | wall s | cpu s | peak RSS MiB | output bytes | change wall | change cpu | change RSS | change bytes | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| formats-csv | 3 | 22.780 (22.357..23.756) | 24.546 (24.091..25.547) | 248.6 (248.5..248.7) | 6208538 (6208538..6208538) | - | - | - | - | - |
| formats-parquet | 3 | 23.298 (23.172..23.602) | 25.054 (24.909..25.272) | 272.1 (267.9..276.2) | 3500951 (3500951..3500951) | - | - | - | - | - |
| formats-sqlite | 3 | 22.118 (21.917..22.156) | 23.737 (23.642..23.822) | 235.0 (234.7..236.5) | 4318837 (4318837..4318837) | - | - | - | - | - |
| real-replay | 1 | 199.972 | 202.130 | 761.0 | 27640113 | - | - | - | - | insufficient-reps |
| synth-L | 3 | 77.424 (77.394..77.760) | 78.849 (78.808..79.328) | 491.0 (490.8..495.0) | 12354828 (12354828..12354828) | - | - | - | - | - |
| synth-M | 7 | 28.336 (28.115..30.180) | 30.076 (29.823..31.964) | 276.3 (270.4..282.3) | 3522108 (3522108..3522108) | - | - | - | - | - |
| synth-S | 7 | 10.254 (9.307..10.435) | 11.993 (11.175..12.280) | 204.8 (204.0..205.0) | 907876 (907876..907876) | - | - | - | - | - |
| synth-XL | 1 | 269.194 | 269.602 | 1351.2 | 41656034 | - | - | - | - | insufficient-reps |

## Scaling

- cases: synth-S, synth-M, synth-L, synth-XL
- b = 0.678

## Flags

- real-replay: insufficient-reps: 1 counted repetition(s)
- synth-XL: insufficient-reps: 1 counted repetition(s)

## Gate failures

(none)

## Failed repetitions

(none)

## Skipped lines

(none)
