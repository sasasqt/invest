# Benchmark history

The original GA-2026-10-31T001744Z audit recorded zero samples because its worker lacked isolation. A separately authorized runtime recovery then measured synth-S remotely. Original blocked rows remain historical records, not timings.

| Run / job | Source / Python | Overall result | Valid measured samples | Median wall seconds |
|---|---|---|---:|---:|
| [41184820796 / 124489509595](https://github.com/sasasqt/invest/actions/runs/41184820796/job/124489509595) | audited / 3.11 | success | 7 | 4.722485291 |
| [41184820796 / 124489509444](https://github.com/sasasqt/invest/actions/runs/41184820796/job/124489509444) | audited / 3.13 | success | 7 | 9.687099363 |
| [41184820796 / 124489509603](https://github.com/sasasqt/invest/actions/runs/41184820796/job/124489509603) | control / 3.11 | temporary-filesystem runner failure | 7 | 8.735382691 |
| [41186347445 / 124493939298](https://github.com/sasasqt/invest/actions/runs/41186347445/job/124493939298) | audited / 3.13 | known main test failure | 7 | 9.939584617 |
| [41186347445 / 124493939518](https://github.com/sasasqt/invest/actions/runs/41186347445/job/124493939518) | audited / 3.11 | known main test failure | 7 | 6.276477057 |
| [41186347445 / 124493939428](https://github.com/sasasqt/invest/actions/runs/41186347445/job/124493939428) | control / 3.11 | success | 7 | 8.533921221 |

Each row retains one warm-up plus seven measurements in raw.jsonl, including failed overall runs. Timings include subprocess startup and exclude semantic hashing. Hardware, Python/library variants and workload context differ; no matched regression baseline, scaling or speedup is claimed. Memory peaks, M/L/XL and format comparisons remain unmeasured. See [runtime validation](../2026-10-31-runtime-validation.md) for source/runner identities, correctness-gate limits and complete status.

## Semantic gate version 2

Earlier measurements at the recorded version-1 runner revisions omitted compressed CSV tables and other unrecognized files from the hash gate. They remain historical measurements, not proof of equality for those omitted artifacts. Their raw lines are unchanged. New version-2 samples cover all files by a disclosed comparison method; compressed tables are decompressed and ledger values retained. Different gate versions and hardware are not a matched performance comparison.

| Job | Source / Python | Overall status | Gate v2 measured samples | Median wall seconds |
|---|---|---|---:|---:|
| [124557059770](https://github.com/sasasqt/invest/actions/runs/41208034002/job/124557059770) | audited / 3.13 | known main test failure | 7 | 5.372929151 |
| [124557059691](https://github.com/sasasqt/invest/actions/runs/41208034002/job/124557059691) | control / 3.11 | success | 7 | 5.828128028 |
| [124557059601](https://github.com/sasasqt/invest/actions/runs/41208034002/job/124557059601) | audited / 3.11 | known main test failure | 7 | 6.880967375 |
