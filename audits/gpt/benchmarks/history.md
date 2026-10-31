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
