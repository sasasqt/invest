# Isolated audit runner

Linux/Docker tooling for an offline, containerized audit of one pinned source revision: boundary probes, installed-environment checks, full-suite results and synth-S measurements. Each pull request that changes the runner records the tested runner and source revisions, its results and its remaining failures. Without Docker only the host-side unit tests can run.

This tooling supplies the execution path missing from the original audit. It keeps source execution inside an offline container, verifies installed versions, stages three genuine workspace wheels, runs the full suite/coverage and independent installs, and records seven timed synth-S repetitions after a warm-up. It does not implement product fixes, merge PRs, publish comments or access reserved observations.

## Files

- `isolated_runner.py`: host-side source identity checks, credential-free Git metadata staging, immutable image capture and restricted container launch.
- `output_collection.py`: descriptor-based, no-follow collection into a private host snapshot; validates summaries and bounds files, bytes, entries and depth before upload.
- `collection_checks.py`: real Docker controls for hostile output and ordinary evidence, using generated host-only canaries, plus `test_output_collection.py` and `test_execution_logs.py` regression tests.
- `test_host_safety.py`: runs the real host runner with a stand-in Docker command to check that `[tool.uv]` settings, file names and build output from the audited source cannot steer host-side uv or start GitHub workflow commands, and that the Dockerfile pulls no unpinned frontend image.
- `runner_workload.py`: boundary checks before product imports, installed-wheel tests, coverage JSON, slow tests, hash-seed repeat, independent installs and synth-S measurements.
- `verify_installed.py`: version/marker checks and workspace import origins.
- `ci_evidence.py`: distinguish fresh job executions from historical jobs copied into newer workflow attempts.
- `verify_snapshot.py`: request/file identity checks without interpreting raw observations. Missing input is blocked; mismatched or unsafe input is rejected.
- `build-requirements.txt`: six hash-pinned auditor build dependencies. These live in a separate build environment, so Hatchling's dependencies cannot replace the project's locked runtime packages.
- `.github/workflows/audit-runtime.yml`: conditional workflow. It runs host/Docker collection checks on Python 3.11/3.13, then both full audit jobs. Source is resolved once from current main or an explicit manual revision; a historical control is optional and explicitly labeled.

## Invocation on a Docker-capable runner

The source must be a genuine Git checkout at the exact requested revision, with its object store available. A source archive without a Git database is insufficient for provenance-sensitive workflow tests.

```sh
python isolated_runner.py --source /path/to/checkout \
  --expected-sha 90b5ca038155b97833b120baa57dfecd05d6f641 \
  --python-version 3.11 --output /path/to/new-audit-output
```

The host performs metadata-only lock checks, with uv's configuration discovery switched off (`--no-config`) so `[tool.uv]` settings in the audited source cannot steer host-side uv, and verified downloads/image setup. The image uses Docker's built-in Dockerfile frontend, so no unpinned frontend image is pulled. It stages only tracked source files plus real commit objects and freshly generated minimal Git configuration; credentials, hooks, logs, host homes and Docker sockets are not mounted into the execution container. Network is disabled, root filesystem and inputs are read-only, capabilities are dropped, privilege escalation is disabled, the container UID is unprivileged, and writable output is isolated. Failed boundary probes stop product execution.

The workflow uses two Python versions and read-only repository permissions; checkout credentials are not persisted. Output upload is limited to the evidence directory. Source commits, image IDs, runtime versions and resource limits are recorded. The initial benchmark scope is synth-S only; M/L/XL, storage-format benchmarks, memory peaks and historical replay remain future work. No speedup/regression comparison is possible without a matched baseline.

Metadata-only uv checks explicitly select the host interpreter, avoiding inherited UV_PYTHON values for an interpreter absent from that host. Test and build temporary files use disk-backed `/work/tmp` inside the private writable workspace, while the 2 GiB memory, two-CPU and 256-process limits remain enforced. This avoids exhausting the separate 256 MiB `/tmp` mount across repeated test suites.

## Semantic output gate, version 2

Every benchmark invocation saves a per-file semantic manifest after timing. Compressed CSV
tables are decompressed and hashed; their gzip header timestamps are excluded. JSON and JSONL
retain numeric values, identities, row order and substantive fields, while the predeclared
`created_at`, `recorded_at`, `retrieved_at` and `created_utc` fields and output-root strings are
normalized. Plain CSV bytes are hashed. Markdown and other declared UTF-8 text normalize only
the output root. Other file types receive a raw-byte comparison rather than being silently
skipped. PNGs must exist and be nonempty; rendered pixels are not compared, while source tables
participate in the gate. Invalid compressed data fails the gate with its evidence retained.

Samples and summaries identify semantic-gate version 2. Earlier version-1 timing samples remain
historical measurements, with a narrower gate that omitted compressed tables and other
unrecognized artifacts. Do not claim those samples prove equality of the omitted files or pool
them into a matched version-2 comparison without a fresh equivalent run.

## Execution limits

Container removal is verified before collecting its writable output. The collector
opens the work/results root and descendants through directory descriptors with
no-follow flags. It rejects file/directory/root links, hard links, special files,
cross-device entries and changing files. Upload receives a newly created private
snapshot, never the original work tree or preserved links. All three printed
summaries are read from that snapshot and JSON-escaped for logs. Host-side errors
and a failed image build's output can quote audited names, so they are printed as
single JSON-escaped lines (`AUDIT_RUNNER_ERROR`, `AUDIT_IMAGE_BUILD_LOG`) that cannot
start GitHub workflow commands. Rejection leaves
`collection.json` and a failed runner result without a partially collected tree.

Collection defaults are 16 MiB per file, 128 MiB total, 4,096 entries and 32 nested
directories; printed JSON summaries are limited to 64 KiB, 32 nesting levels and
4,096 nodes. Container stdout/stderr
uses an 8 MiB host buffer and a 6,600-second deadline; exceeding either fails the
run, retains bounded logs and removes the container. These collection/log limits
do not impose a disk quota on the live writable work directory. Use a disposable
runner with an appropriate disk budget. Collection uses Linux/POSIX descriptor
APIs and fails closed when unavailable; Windows collector execution is unsupported.

The collection workflow tests file, directory, root and each summary link against
generated host-only canaries. It also rejects FIFO, hard-link and oversized
output, checks all normal boundary probes, and proves ordinary evidence still
collects. It uploads only the host evidence directory. Run the host regression
tests with `python -m unittest -v test_guards test_output_collection test_execution_logs test_host_safety`.
Run `python collection_checks.py --python-version 3.11 --output /path/to/new-output`
on a Docker-capable disposable host and repeat with Python 3.13. These generated
fixtures do not read real secrets or market observations, run a product benchmark,
or establish independently reviewed resolution of every runner-security concern.

Local guard tests verify command construction, source staging, hash checks and classification behavior. Each actual execution must also pass its kernel/file/network/process denial probes before product imports. A previous successful trial does not certify another host. Keep runner-code identity separate from audited-source identity; pull-request checkout merge commits must have matching runner blobs before attributing evidence to a PR head.

Results must be checked at the exact runner revision; local guard tests are not proof of a working Docker boundary. Linux execution only; Windows execution is not claimed. The main-code test failure remains distinct from runner failures and benchmark correctness.

Each run resolves its source once for the whole matrix; earlier trials keep their
original source identities and failures.
Test-suite durations and synthetic workflow samples remain separate evidence.
