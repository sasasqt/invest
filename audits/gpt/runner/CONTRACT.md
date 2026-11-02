# Audit runner contract

These rules hold on Linux and Windows hosts. The container side always runs Linux.
`contract.py` checks the host rules P1, Q1-Q5 and I1-I2 while `CONTRACT_CHECKS=1`
(P2 and P3 are always enforced by the code, and the suites check W1-W3); every test
suite, the CI host-test steps and the CI Docker controls step set it, production
runs do not.
A failed check raises `ContractViolation` (an `AssertionError`), never an ordinary
rejection.

## Preconditions

- **P1** Collection starts only after Docker reports the container removed.
  Checked in `isolated_runner.main` before `collect_workload`.
- **P2** The collection destination is outside the writable work folder and does
  not exist. Always enforced: `collect_results` raises `ValueError` otherwise.
- **P3** The source checkout's HEAD equals the expected 40-hex SHA. Always enforced:
  `stage_source` raises `ValueError` otherwise.

## Postconditions

- **Q1** Status `collected`: the snapshot holds only regular files and folders. Each
  file's bytes equal a source regular file with one link, on the results folder's
  volume, reached without any link or reparse point. Counts and bytes are within
  the limits, and every file has a SHA-256 record. Checked after every successful
  collection (`check_collected`), against the source tree.
- **Q2** Status `rejected`: the destination does not exist and no temporary snapshot
  is left; `collection.json` records the rejection. Checked on every rejection
  (`check_rejected`).
- **Q3** Every runner log line that carries untrusted text is one line, contains no
  `#`, does not start with `::`, and its JSON part decodes to the original value.
  Checked in `log_line`.
- **Q4** Every staged source file's Git blob hash equals the commit's entry, on
  every host, and the staged tree holds exactly the commit's paths. Always enforced
  for the bytes read from Git (with replace refs and inherited `GIT_*` variables
  ignored); checked again on the written file in `stage_source`. No path enters
  `.git`, and no two committed paths may reach the same staged file or folder.
- **Q5** Host-side uv runs with `--no-config`. Checked in `host_uv`.

## Invariants

- **I1** The host reads bytes only from an output entry whose own `lstat` showed a
  file that is no link, and whose opened descriptor is a one-link regular file with
  the same identity: device, inode, size and times on POSIX; volume and file ID in
  the path walk, because Windows can answer a by-name stat from the folder entry,
  whose size and times may lag the open handle's. In the descriptor walk (the
  default on POSIX) every folder is reached through no-follow directory
  descriptors. In the path walk (the default on Windows) each path component is
  checked to be no reparse point just before the open, and each folder again after
  it was listed. P1 excludes the container as a concurrent writer. Another local
  account that can write the work folder (POSIX: mode 0777, so that any container
  UID, including one remapped by rootless Docker, can write it; Windows: the
  inherited ACL) is not excluded: the identity checks still keep its files out of
  the snapshot, but it can change or spoil the evidence, so run audits on a
  single-user host. Checked in `read_opened`.
- **I2** On POSIX, where both walks run, the descriptor walk and the path walk give
  the same outcome, records and summaries for the same unchanging tree whose paths
  fit the host's path length limit (the path walk cannot open a longer path; the
  descriptor walk can). Checked after every collection with the descriptor walk,
  except a rejection for a change during the walk (only tests can cause one, since
  P1 excludes a writer) or for an `OSError`.

## Container workload and snapshot check (checked by the suites)

These run inside the Linux container or on raw input, not in the host process, so
`contract.py` does not check them; `test_guards.py` does, and the CI Docker controls
exercise W1 and W2 in a real container.

- **W1** `boundary.json` reports `no_capabilities` true only when the permitted,
  effective and bounding capability sets are all empty (and the ambient set, where
  listed). The effective set alone is empty for any non-root process, so it cannot
  show a missing `--cap-drop=ALL`. Checked in `runner_workload.capabilities_dropped`.
- **W2** No process a workload step started still runs when the next step starts:
  every step runs in its own session, and every process left in that session is
  killed once the step ends, also one that made its own process group (GNU
  `timeout`, a shell with job control). In the container, where the workload is
  PID 1, every other process is then killed and reaped as well, so one that started
  a new session (`setsid`) is stopped too and no zombie holds a slot of
  `--pids-limit`. Outside a container (host tests) a process that starts a new
  session escapes. Checked in `runner_workload.execute`.
- **W3** `verify_snapshot` reports a missing snapshot folder, `snapshot.json` or raw
  file as `blocked` (exit 2) and every other wrong input (a missing or unreadable
  `--expected` manifest, a manifest or entry of the wrong shape, an unsafe,
  Windows-rooted or repeated raw path, an entry that exists but is not a regular
  file, a hash mismatch) as `rejected` (exit 2). The manifest's own entries are
  checked before the snapshot is looked at, so a bad manifest is rejected even when
  the snapshot is missing. It never ends with a traceback.

## Deliberate behaviour differences from the Linux-only runner (PR #32)

- Source files are staged from Git's object store, not from the checked-out files,
  so a checkout whose files differ from the commit (CRLF line ends from Git on
  Windows, or local edits) still stages exactly the committed bytes.
- Source paths and output names that Windows or an artifact zip would read
  differently are refused on every host: reserved device names (`CON`, `NUL`,
  `COM1`...), names ending in a dot or space, `\ / : * ? " < > |`, control
  characters, non-UTF-8 names, names shaped like an NTFS short name (`PROGRA~1`),
  and source paths that clash when case is ignored.
- Source paths that enter Git's own folder (`.git` in any case, or `GIT~1`) are
  refused before anything is written. PR #32 failed later on such a commit, when
  the checked-out bytes did not match.
- The staged copy's index is built with no inherited `GIT_*` variables, no
  system or global Git configuration, no file system monitor and an empty hooks
  folder. Git before 2.32 cannot leave out the global configuration, so it is
  refused before staging.
- A Docker daemon that cannot be reached, or does not report Linux containers,
  gives a `blocked` result (exit 2) before any source is read.
- `git`, `uv` and `docker` are run only from absolute `PATH` folders, never from the
  current folder or a relative `PATH` entry (Windows searches the current folder
  first), so a program committed in the audited checkout cannot run on the host.
- `--source` may name a subfolder of the checkout, or a linked worktree; the whole
  commit is staged, with objects read from the repository's common Git folder.
- A used `--output` folder (one that exists and is not empty) is refused with exit
  1 before anything runs. PR #32 reused it, so an earlier `runner.json` survived a
  later run that failed before writing its own.
- The CA bundle for the image build comes from the system bundle (not on Windows,
  where `/etc/ssl/...` would name a folder on the current drive that any local user
  may create), else Python's default CA file, else (Windows) the certificate store
  exported as PEM.
- On a Windows host the container's outside-file and host-process probes are not
  run, so `boundary.json` lacks `outside_fixture_absent` and
  `host_process_not_visible`, and its child check is named
  `child_inherits_env_denial`: a Windows path or process ID names nothing inside
  the Linux container, so those checks would pass whatever leaked.
- Every host program runs with captured output through `run_captured`, which kills
  it at its timeout and returns at once. `subprocess.run` on Windows reads the pipes
  to their end after the kill, so a child that a launcher started (Git for Windows'
  `cmd\git.exe`, a Docker CLI plugin such as buildx) kept it waiting.
- `verify_snapshot` refuses raw paths with `\` or `:` in any part on every host;
  on Windows such a path would name a drive, a share or a stream.
