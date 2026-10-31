# Runtime recovery validation — 31 October 2026

## Outcome

The user authorized the proposed workflow and draft pull request after the earlier output-only recovery report. [Draft PR #32](https://github.com/sasasqt/invest/pull/32) adds `.github/workflows/audit-runtime.yml` and the isolated runner; it does not merge the existing product-test fix in PR #31. The execution environment remains GitHub-hosted Linux/Docker. No repository build, import, test or benchmark ran in the managed worker without its missing isolation boundary.

Final configuration results are recorded below after artifact verification. This report supplements, rather than retroactively rewriting, the earlier blocked audit and execution-recovery report. The full repository audit remains incomplete. Detailed records are in [2026-10-31-runtime/](2026-10-31-runtime/).

## Identities and fixes

- Audited source: `90b5ca038155b97833b120baa57dfecd05d6f641` (110 tracked blobs).
- Existing test-fix control: `a943dbf4a318fc2cb12f93b1d2a875ee51774572` from [PR #31](https://github.com/sasasqt/invest/pull/31). It is a separately labeled control, not main or a merged fix.
- Final executable runner revision: `b4c9a911d0856d1b9c4fd675893d9b61b366414f`.
- Documentation-only PR head: `456592a8afa3a20c39b8ca95b9786c6e16d2d3dc`. All nine executable/configuration blob identities match the tested runner; its README is the only later change. The documentation commit skips redundant CI.
- Lock SHA-256: `4e14019237eefe5b318cfe68f5544729838566abfae279a75ba4d4b6b7eaa330`.

The initial workflow trial, [run 41184648865](https://github.com/sasasqt/invest/actions/runs/41184648865), stopped before Docker because an inherited `UV_PYTHON` selected a host interpreter that was not installed. Metadata-only `uv lock --check` and export now explicitly select the actual host interpreter. A controlled non-executing reproduction distinguished the missing-interpreter failure from a successful explicit-interpreter check. The runtime-specific requirements remain universal lock exports, with markers applied and installed versions verified inside each container.

The next trial, [run 41184820796](https://github.com/sasasqt/invest/actions/runs/41184820796), validated both audited Python versions and all eight synthetic runs in each of its three jobs. Its Python 3.11 control passed the full suite and hash-seed repeat, then exhausted the 256 MiB `/tmp` filesystem during independent mining tests: `test_cli_lookback_formula_still_requires_history` and `test_export_signals_bundle` reported `OSError: [Errno 28] No space left on device` while writing synthetic fixture bundles. These are retained runner-environment failures. The runner now creates and exports disk-backed `/work/tmp` in its existing private writable mount. Memory (2 GiB), CPU (two cores), process (256), network and privilege limits are unchanged. No product assertion was relaxed, and no source fixture or lockfile was edited.

Thirty local runner/guard contract tests pass, including the temporary-directory launch requirement; format and lint pass. A fresh standard-library subprocess also confirms that `TMPDIR` routes temporary directories to the chosen disk workspace. These checks are distinct from actual Docker execution evidence.

## Final execution

[Final run 41186347445](https://github.com/sasasqt/invest/actions/runs/41186347445), using the final executable revision above:

| Source / runtime | Full suite | Repeat and independent tests | synth-S median / range | Host CPU |
|---|---|---|---|---|
| [audited / 3.11](https://github.com/sasasqt/invest/actions/runs/41186347445/job/124493939518) | 1 failed, 585 passed in 303.18s (0:05:03) | repeat 585 passed / 1 known failure; independent 162 passed, 128 passed / 1 known failure, 240 passed | 6.276477 s / 6.226811–6.326835 s | AMD EPYC 9V74 80-Core Processor |
| [audited / 3.13](https://github.com/sasasqt/invest/actions/runs/41186347445/job/124493939298) | 1 failed, 585 passed in 443.40s (0:07:23) | not run on this version | 9.939585 s / 9.839160–10.191495 s | AMD EPYC 7763 64-Core Processor |
| [control / 3.11](https://github.com/sasasqt/invest/actions/runs/41186347445/job/124493939428) | 587 passed in 406.71s (0:06:46) | repeat 587 passed; independent 162 / 130 / 240 passed | 8.533921 s / 8.434493–8.583972 s | AMD EPYC 7763 64-Core Processor |

All three final jobs passed their 12 boundary checks and 30 helper tests, verified the 26 locked runtime distributions and installed workspace imports, and completed eight valid synthetic workflow invocations each (one warm-up, seven measurements). The control passed every validation command, including all independent installs; the temporary-storage errors are absent. Its full suite and hash-seed repeat both report 587 passed.

Both audited main suites retain `INV-COMMON-001 / REVIEW-22`: `test_factor_from_another_experiment_is_refused` selected a factor absent from the second confirmation family, so the membership guard fired before the expected experiment-identity guard. The Python 3.11 repeat and independent mining suite reproduced that same existing failure. These are the only final command failures. The overall workflow remains red for those expected baseline outcomes; it is not presented as a green main audit. The two audited jobs in the earlier tmpfs trial happened to pass 586 tests, demonstrating why filesystem-dependent success is not a fix.

Regular CI at the executable PR revision also completed freshly: both full suites, the wheel job and independent mining job failed solely on the same known test; data and evaluation independent jobs passed. Exact jobs and failure summaries are retained in `regular-ci.json`. PR #31 remains separate and unmerged. No baseline rerun was requested after these known failures.


## What the evidence proves

Each accepted artifact ZIP was downloaded through the GitHub connector and matched its GitHub-reported SHA-256 digest before inspection. No archive paths were extracted or executed. A trusted verifier independently checked exact tracked source blob maps against the committed remote trees, source SHA agreement across identity/launch/result records, all 12 boundary probes, immutable image identity, resource limits, 26 applicable installed versions against the frozen lock export, workspace import origins, validation command exits, and the raw sample/summary agreement. Full per-command outcomes, graphs, coverage totals and sample rows are persisted beside this report; GitHub artifacts additionally contain complete logs and coverage JSON (30-day workflow retention).

Pull-request workflows check out a GitHub test-merge commit by default. The job logs' actual runner checkout and separately pinned source checkout are recorded in `checkout-identities.json`; all ten runner/workflow blobs were compared with their stated PR heads. A workflow head SHA alone is not treated as the product revision or sufficient source proof.

The boundary checks establish the tested container's unprivileged UID, no-new-privileges, dropped capabilities, denied host fixture/process/environment/socket access, read-only source access, denied outbound connection, inherited child denials and writable private output. They ran before product imports. They are observed controls on these hosts, not a general sandbox security certification. The base image digest and final image ID are retained per job. Runtime wheel downloads enforce hashes from `uv.lock`; six separately hash-pinned build dependencies live in a separate environment.

The Python 3.11 jobs additionally repeat the full suite with `PYTHONHASHSEED=12345` and test three independent installations. The evaluation environment checks that mining is absent. Both versions test installed workspace wheels, type/lint/format checks, documentation links and three CLI entry points. Coverage JSON and the slowest 25 tests are retained. These are remote results, not six locally executed CI jobs or Windows parity.

## Benchmark interpretation

Each synth-S case uses 20 instruments × 300 sessions and 20 search trials, one warm-up and seven measured repetitions. Each invokes the repository's published synthetic workflow, with a 60-second per-case timeout, one thread for BLAS/OMP, no parallel benchmark cases within that job, and process startup included. Semantic hashing occurs after timing. Numeric JSON/JSONL/CSV outputs must match that job's warm-up after the declared timestamp and output-root normalization; PNGs must be present/nonempty and their source tables participate in hashing. This is a repeatability gate, not an independent financial correctness oracle.

Raw warm-ups, measurements, CPU times, output bytes, semantic hashes, hardware, limits, source/runner identities, GitHub jobs and original run failures are preserved in `benchmarks/raw.jsonl`. The failed temporary-filesystem trial remains labeled as such. Absolute medians are not a speedup or regression finding: hosts and interpreter/library variants differ, there is no matched comparison baseline, and GitHub-hosted runs were not exclusive machine reservations. Peak memory, M/L/XL scaling, storage formats and throughput are not measured.

## Checkpoint and remaining work

The earlier recovery read 318 additional static lines. This continuation then read another 408 lines in `data-mining-framework/tests/test_evidence.py` and `test_search_and_inference.py`, after matching their original Git blob identities. It confirms the known directory-order selection error at `test_evidence.py:119` and examines evidence identity/horizon/out-of-sample guards, synthetic purged splits, artifact integrity, causal scores and universe filtering. This adds no new independently confirmed product root cause. The combined supplements leave **19,659 unread lines across 78 paths**. Automatic scans and runtime coverage do not count as semantic reading.

The maintained checkpoint now references both static supplements and this runtime evidence. Its original run timestamps, preflight failures and publication facts remain historical records. It must still report `audit_incomplete`. Remaining work includes the unread static ranges, original GA1/GA2 controls, wider format/recovery workflows and benchmarks, remaining portability/advisory/schema/CLI review, research oracle execution and exact historical replay. The latest known test-order defect is an existing PR #31 item, not a newly discovered GA root cause.

The matching raw Yahoo snapshot is still unavailable: 101 recorded JSON files totaling 40,077,185 bytes, including SPY, from 7 October 2026 at 10:32:52 UTC. The committed manifest is an inventory, not those files. No fresh download was substituted and no reserved 2025-onward observation was accessed. Missing historical input blocks exact replay, not completed synthetic execution.

The daily audit remains enabled at 01:15 Europe/Berlin with its original output-only permissions. Its recovery instructions now point to verified runtime evidence and distinguish runner checkout from audited source. This one-time draft-PR authorization does not silently grant that routine permission to modify workflows, open further PRs, merge changes or alter another task. The PR review routine is unchanged.
