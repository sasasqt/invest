# Isolated audit runner

Docker tooling for an offline, containerized audit of one pinned source revision, run in a Linux container from a Linux or Windows host: boundary probes, installed-environment checks, full-suite results and synth-S measurements. Record the tested runner and source revisions, results and remaining failures in the pull request that changes the runner. Without Docker only the host-side unit tests can run.

This tooling supplies the execution path missing from the original audit. It keeps source execution inside an offline container, verifies installed versions, stages three genuine workspace wheels, runs the full suite/coverage and independent installs, and records seven timed synth-S repetitions after a warm-up. It does not implement product fixes, merge PRs, publish comments or access reserved observations.

## Files

- `isolated_runner.py`: host-side source identity checks, credential-free Git metadata staging, immutable image capture and restricted container launch.
- `output_collection.py`: link-free collection into a private host snapshot (no-follow directory descriptors on POSIX hosts, a reparse-point-checking path walk on Windows); validates summaries and bounds files, bytes, entries and depth before upload.
- `CONTRACT.md`, `contract.py`: the host-side rules (preconditions, postconditions, invariants) and their checks, which run when `CONTRACT_CHECKS=1`. Every test suite and the CI host steps switch them on.
- `collection_checks.py`: real Docker controls for hostile output and ordinary evidence, using generated host-only canaries, plus `test_output_collection.py` and `test_execution_logs.py` regression tests.
- `test_host_safety.py`: runs the real host runner with a stand-in Docker command to check that uv settings (such as `cache-dir`), file names, build output and container output from the audited source cannot steer host-side uv or start GitHub workflow commands, and that the Dockerfile pulls no unpinned frontend image.
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

The host performs metadata-only lock checks, with uv's configuration discovery switched off (`--no-config`) so uv settings in the audited source (such as `cache-dir`) cannot steer host-side uv, and verified downloads/image setup. A project that needs resolution settings such as `exclude-newer` therefore fails the host lock check; a custom index still passes it, and only the image build's hash checks then apply. Known limit: path, Git or URL dependency sources in the audited `[tool.uv.sources]` are still resolved on the host, so the lock check can read a host path that the source names; nothing is written there. The image uses Docker's built-in Dockerfile frontend, so no unpinned frontend image is pulled. It stages only tracked source files, read from Git's object store so that a checkout with CRLF line ends (Git on Windows) still stages the committed bytes, plus real commit objects and freshly generated minimal Git configuration. Paths into `.git`, names Windows would read differently (reserved names, NTFS short-name forms such as `PROGRA~1`, trailing dots), case clashes and repeated paths are refused, and the staged index is built without inherited `GIT_*` variables, replace refs, system or global Git configuration, a file system monitor or hooks; credentials, hooks, logs, host homes and Docker sockets are not mounted into the execution container. Network is disabled, root filesystem and inputs are read-only, capabilities are dropped, privilege escalation is disabled, the container UID is unprivileged, and writable output is isolated. Failed boundary probes stop product execution.

The workflow uses two Python versions and read-only repository permissions; checkout credentials are not persisted. Output upload is limited to the evidence directory. Source commits, image IDs, runtime versions and resource limits are recorded. The initial benchmark scope is synth-S only; M/L/XL, storage-format benchmarks, memory peaks and historical replay remain future work. No speedup/regression comparison is possible without a matched baseline.

Metadata-only uv checks explicitly select the host interpreter, avoiding inherited UV_PYTHON values for an interpreter absent from that host. Test and build temporary files use disk-backed `/work/tmp` inside the private writable workspace, while the 2 GiB memory, two-CPU and 256-process limits remain enforced. This avoids exhausting the separate 256 MiB `/tmp` mount across repeated test suites.

## Windows hosts

The host side (staging, image build, launch and collection) also runs on Windows
with Docker Desktop in Linux-container mode. The runner talks to
`npipe:////./pipe/docker_engine`, runs the container as UID and GID 65534, and
takes the build's CA bundle from the system bundle, else Python's default CA file,
else the Windows certificate store exported as PEM. A daemon that cannot be reached,
or does not report Linux containers, gives a `blocked` result (exit 2) before any
source is read. `git`, `uv` and `docker` are taken only from absolute `PATH`
folders, never from the current folder, which Windows otherwise searches first: a
program committed in the audited checkout cannot run on the host even when the
runner starts inside it. The
container's outside-file and host-process probes are not run from a Windows host,
since a Windows path or process ID names nothing inside the Linux container, so
`boundary.json` lacks `outside_fixture_absent` and `host_process_not_visible`
there, and its child check (`child_inherits_env_denial`) covers the environment
only. The `host-tests-windows` job runs the four host test modules on
`windows-2025` with Python 3.11 and 3.13.

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

Container removal is verified before collecting its writable output. On POSIX
hosts the collector opens the work/results root and descendants through directory
descriptors with no-follow flags. Windows has no such descriptors: there it checks
that no path component is a reparse point (symbolic link, junction or WSL link)
just before each open, checks each folder as soon as it is listed and again after
walking it, and ties each opened file to the checked name by volume and file ID.
That walk relies on the verified container removal, so no process can swap an
entry during collection. Both walks reject file/directory/root links, hard links, special files,
cross-device entries, a different file opened than the one checked by name, and a file
that changes while it is read. (The Windows walk compares only volume and file ID
between the check and the open, because a by-name stat there may show stale size and
times.) Upload receives a newly created private
snapshot, never the original work tree or preserved links. All three printed
summaries are read from that snapshot. Every runner `AUDIT_*` log line (container output,
summaries, host errors and a failed image build's output, which can quote audited
names) is one JSON-escaped line with `#` escaped as well, so it cannot carry a GitHub
workflow command (`::` at a line start, or the older `##[` anywhere). Rejection leaves
`collection.json` and a failed runner result without a partially collected tree.

Collection defaults are 16 MiB per file, 128 MiB total, 4,096 entries and 32 nested
directories; printed JSON summaries are limited to 64 KiB, 32 nesting levels and
4,096 nodes. Container stdout/stderr
uses an 8 MiB host buffer and a 6,600-second deadline; exceeding either fails the
run, retains bounded logs and removes the container. These collection/log limits
do not impose a disk quota on the live writable work directory. Use a disposable
runner with an appropriate disk budget. On Windows, an output path longer than
260 characters (without long paths enabled) is unreadable, so collection rejects it.

The collection workflow tests file, directory, root and each summary link against
generated host-only canaries. It also rejects FIFO, hard-link and oversized
output, checks all normal boundary probes, and proves ordinary evidence still
collects. It uploads only the host evidence directory. Run the host regression
tests (they need `packaging`) on Linux or Windows with
`python -m unittest -v test_guards test_output_collection test_execution_logs test_host_safety`.
Run `python collection_checks.py --python-version 3.11 --output /path/to/new-output`
on a Docker-capable disposable host and repeat with Python 3.13. These generated
fixtures do not read real secrets or market observations, run a product benchmark,
or establish independently reviewed resolution of every runner-security concern.

Local guard tests verify command construction, source staging, hash checks and classification behavior. Each actual execution must also pass its kernel/file/network/process denial probes before product imports. A previous successful trial does not certify another host. Keep runner-code identity separate from audited-source identity; pull-request checkout merge commits must have matching runner blobs before attributing evidence to a PR head.

Results must be checked at the exact runner revision; local guard tests are not proof of a working Docker boundary. Docker execution is verified on Linux hosts only. On Windows, CI runs only the host-side tests, because GitHub's Windows runners cannot run Linux containers, so an audit on a Windows host is not yet claimed. The main-code test failure remains distinct from runner failures and benchmark correctness.

Each run resolves its source once for the whole matrix; earlier trials keep their
original source identities and failures.
Test-suite durations and synthetic workflow samples remain separate evidence.
