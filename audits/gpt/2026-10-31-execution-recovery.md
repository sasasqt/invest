# Execution recovery — 31 October 2026

## What was tested

Two fresh GitHub Actions checks were launched on the exact audited main commit `90b5ca038155b97833b120baa57dfecd05d6f641`. Frozen dependency installation, formatting, lint and type checks succeeded. Each full suite then reproduced the same known test defect:

| Runtime | Result | Test duration | Evidence |
|---|---|---:|---|
| Python 3.11.18 | 585 passed, 1 failed | 305.57 s | [fresh job](https://github.com/sasasqt/invest/actions/runs/37851091069/job/124479741062) |
| Python 3.13.18 | 585 passed, 1 failed | 346.04 s | [fresh job](https://github.com/sasasqt/invest/actions/runs/37851091069/job/124480821393) |

`test_factor_from_another_experiment_is_refused` picks the first factor file returned by directory iteration. When that factor was not tested by the second search, the membership guard refuses it before the experiment-identity guard that the test expects. This independently reproduces existing `INV-COMMON-001 / REVIEW-22`; it is not a new discovery.

An existing fix is available in [PR #31](https://github.com/sasasqt/invest/pull/31), head `a943dbf4a318fc2cb12f93b1d2a875ee51774572`. Reading the patch shows that it deliberately selects a factor shared by both searches, checks their distinct experiment identities, and separately tests a factor absent from the second search. All six current-head CI jobs are successful. Both full suites report 587 passed. No product fix was duplicated, and no PR was approved or merged. Main still has the old test at the final check.

Those control jobs are existing same-day evidence read by this task, not additional jobs launched by it. Suite durations from different jobs/interpreters are not controlled performance comparisons.

## Recovery changes

The prepared helpers pass **30 local targeted tests**, including missing/tampered snapshot files, request mismatch, reserved-date rejection, path escapes/symlinks, stale copied CI jobs, queued jobs, wrong revisions, version-marker selection, dependency drift, unprivileged launch options, immutable image requirements and real Git commit preservation without credential configuration. Formatting, lint and Python parsing pass. Workflow YAML parsing, matrix versions and read-only repository permission were checked.

Six build dependencies were downloaded and their SHA-256 values cross-checked with PyPI metadata. They are pinned in a separate auditor build environment, closing the unpinned Hatchling preparation gap without changing project manifests or uv.lock. Runtime requirements remain the project's original lock export.

The runner implementation is saved under `audits/gpt/runner/`. Its whole-container execution has **not** been tested: the current worker still lacks Docker. The no-Docker control exits blocked before product execution. Namespace/Landlock failures are not relabeled as a successful sandbox. QEMU's software-emulation option was rejected because its own security documentation says it must not be relied on for guest isolation.

No project test, workflow or benchmark ran locally. Remote checks are explicitly identified above. The proposed runner would generate coverage JSON, slow-test output, installed-graph evidence, independent-install results and a bounded synth-S benchmark with all raw samples retained. It does not claim those outputs already exist. There are **zero measured benchmark samples** in this recovery run.

## Freshness correction

GitHub's latest workflow attempt carries forward four successful jobs from 8 October with new job IDs and the latest attempt number. Only the Python 3.11 and 3.13 jobs actually started today. `ci_evidence.py` uses exact head identity and job start timestamps; it does not call six jobs fresh merely because the latest workflow attempt exposes them. Failures, pending jobs and absent evidence remain distinct.

## Checkpoint and dataset

The original 110-file source identity remains valid. The earlier investigation resumed 318 static lines in the confirmation ledger and historical baseline; its supplemental checkpoint leaves 20,067 unread lines across 80 paths. Runtime failures do not erase those reads or prevent further static review.

The matching raw Yahoo archive was not located. The complete `/invest` Library inventory, prior filename/content searches, repository README and Personal Context supplied only the external path `/mnt/project-files/data/yahoo-test/`, which is absent here. Exact replay needs the 101 recorded JSON files (40,077,185 bytes), including SPY, from the 7 October 10:32:52 UTC snapshot. The committed snapshot manifest is an inventory, not the data. No fresh vendor download or reserved 2025-onward observation was used.

The snapshot helper checks matching recorded request/file identity and hashes; unavailable input is a blocked replay, not proof of a repository defect. Missing historical input does not block synthetic tests or benchmarks on a working runner.

## Remaining activation

The proposed `.github/workflows/audit-runtime.yml` is saved as `audits/gpt/runner/workflow-proposal.yml`. It has not been installed or run. Activating it and opening a draft PR exceed the original audit-only branch/folder and no-PR permissions. The existing daily audit remains enabled at 01:15 Europe/Berlin; its recovery addendum preserves all data, model, publication and other task boundaries.

Next concrete step: activate and execute the proposed isolated runner after that scope is authorized, then evaluate its boundary proof before accepting tests or benchmark results. Historical replay separately requires the original archive. The full repository audit remains incomplete.

## Primary sources

- [Original audit](https://github.com/sasasqt/invest/blob/b57bd4334bd702d4649982f616d9bdaaefb728ce/audits/gpt/2026-10-31.md)
- [Existing fix PR #31](https://github.com/sasasqt/invest/pull/31)
- [Snapshot provenance](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/runs/yahoo-test/2026-10-07/README.md)
- [QEMU security boundary](https://www.qemu.org/docs/master/system/security.html)
- [Docker execution controls](https://docs.docker.com/reference/cli/docker/container/run/)
