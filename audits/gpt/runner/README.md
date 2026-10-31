# Isolated audit runner — draft execution trial

Status on 31 October 2026: **30 local guard tests pass; static format/lint checks pass. The complete Docker runner has not been executed.** Docker and its socket are unavailable in the current worker. No benchmark samples have been measured.

This tooling supplies the execution path missing from the original audit. It keeps source execution inside an offline container, verifies installed versions, stages three genuine workspace wheels, runs the full suite/coverage and independent installs, and proposes seven timed synth-S repetitions after a warm-up. It does not implement product fixes, merge PRs, publish comments or access reserved observations.

## Files

- `isolated_runner.py`: host-side source identity checks, credential-free Git metadata staging, immutable image capture and restricted container launch.
- `runner_workload.py`: boundary checks before product imports, installed-wheel tests, coverage JSON, slow tests, hash-seed repeat, independent installs and synth-S measurements.
- `verify_installed.py`: version/marker checks and workspace import origins.
- `ci_evidence.py`: distinguish fresh job executions from historical jobs copied into newer workflow attempts.
- `verify_snapshot.py`: request/file identity checks without interpreting raw observations. Missing input is blocked; mismatched or unsafe input is rejected.
- `build-requirements.txt`: six hash-pinned auditor build dependencies. These live in a separate build environment, so Hatchling's dependencies cannot replace the project's locked runtime packages.
- `.github/workflows/audit-runtime.yml`: executable draft workflow. It runs both audited Python versions and a labeled Python 3.11 control at the test-only PR #31 revision.

## Invocation after a Docker-capable runner is available

The source must be a genuine Git checkout at the exact requested revision, with its object store available. The 110-file snapshot without a Git database is insufficient for provenance-sensitive workflow tests.

```sh
python isolated_runner.py --source /path/to/checkout \
  --expected-sha 90b5ca038155b97833b120baa57dfecd05d6f641 \
  --python-version 3.11 --output /path/to/new-audit-output
```

The host performs metadata-only lock checks and verified downloads/image setup. It stages only tracked source files plus real commit objects and freshly generated minimal Git configuration; credentials, hooks, logs, host homes and Docker sockets are not mounted into the execution container. Network is disabled, root filesystem and inputs are read-only, capabilities are dropped, privilege escalation is disabled, the container UID is unprivileged, and writable output is isolated. Failed boundary probes stop product execution.

The workflow proposal uses two Python versions and read-only repository permissions; checkout credentials are not persisted. Output upload is limited to the evidence directory. Source commits, image IDs, runtime versions and resource limits are recorded. The initial benchmark scope is synth-S only; M/L/XL, storage-format benchmarks, memory peaks and historical replay remain future work. No speedup/regression comparison is possible without a matched baseline.

## Limitations and activation

Local guard tests verify command construction, source staging, hash checks and classification behavior. They do not establish that a real Docker boundary works. The kernel/file/network/process denial probes must pass on the actual execution host before accepting any runtime results.

The user authorized installation of the workflow and creation of a draft PR on 31 October 2026. Results must be checked at the exact runner revision; local guard tests are not proof of a working Docker boundary. Linux execution only; Windows execution is not claimed. The main-code test failure remains distinct from runner failures and benchmark correctness.

Fresh external CI on the audited main revision completed on Python 3.11 and 3.13: 585 passed / 1 failed in each. The known test defect has an existing correction in PR #31. Its current head `a943dbf4a318fc2cb12f93b1d2a875ee51774572` has six successful CI jobs, with 587 passing in both full suites; it has not been merged into main by this task. These timings are test-suite durations with coverage, not software benchmark samples.
