# Audit runner contract

These rules hold on Linux and Windows hosts. The container side always runs Linux.
`contract.py` checks the host rules P1, Q1-Q5 and I1-I2 while `CONTRACT_CHECKS=1`
(P2 and P3 are always enforced by the code, and the suites check W1-W5); every test
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
  The staged object store holds exactly the objects the commit reaches (its
  history, cut at a shallow boundary), never a stash, another branch or an object
  that no commit holds; checked in `stage_source` against `git rev-list --objects`.
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
  UID can write it; Windows: the inherited ACL) is not excluded: the identity
  checks keep out only an entry it swaps between the walk's check by name and the
  read; whatever it writes or swaps in before the walk reaches that entry, before or
  during collection, is collected as evidence, so run audits on a single-user host.
  Checked in `read_opened`.
- **I2** On POSIX, where both walks run, the descriptor walk and the path walk give
  the same outcome, records and summaries for the same unchanging tree whose paths
  fit the host's path length limit (the path walk cannot open a longer path; the
  descriptor walk can). Checked after every collection with the descriptor walk,
  except a rejection for a change during the walk (P1 excludes the container as a
  writer, so only a test or another local account, see I1, can cause one) or for an
  `OSError`. A failure of the check's own reference snapshot (beside the real one;
  its own path, or a full volume) is raised as that `OSError`, never reported as an
  I2 break; with a relative destination, a summary lookup that the path walk's
  full spelling (under the current folder) puts past the limit skips the check
  like a tree path past it.

## Container workload and snapshot check (checked by the suites)

W1-W3 and W5 run inside the Linux container or on raw input, and W4 is a property
of the workflow, not of the host process, so `contract.py` does not check them;
`test_guards.py` checks W1-W3 and W5 and `test_host_safety.py` checks W4. In a real
container the CI Docker controls exercise W1 (they run only the boundary probe), and
the full isolated audit jobs exercise W1, W2 and W5.

- **W1** `boundary.json` reports `no_capabilities` true only when the permitted,
  effective and bounding capability sets are all empty (and the ambient set, where
  listed). The effective set alone is empty for any non-root process, so it cannot
  show a missing `--cap-drop=ALL`. Checked in `runner_workload.capabilities_dropped`.
- **W2** No process a workload step started still runs when the next step starts:
  every step runs in its own session, and every process left in that session is
  killed once the step ends, also one that made its own process group (GNU
  `timeout`, a shell with job control). In the container, where the workload is
  PID 1 (the runner passes `--init=false`, so a daemon set to add an init process
  cannot take that place), every other process is then killed and reaped as well,
  so one that started a new session (`setsid`) is stopped too and no zombie holds a
  slot of `--pids-limit`. Outside a container (host tests) the session scan is best effort:
  a process that starts a new session escapes, and so can a chain that keeps forking
  with each parent exiting at once, since a scan sees only the process IDs listed
  when it began. Checked in `runner_workload.execute`.
- **W3** `verify_snapshot` reports a missing snapshot folder, `snapshot.json` or raw
  file as `blocked` (exit 2) and every other wrong input (a missing or unreadable
  `--expected` manifest, a manifest or entry of the wrong shape, including a
  negative size or a SHA-256 that is not 64 lower-case hex digits, an empty `files`
  object, an unsafe, Windows-rooted or repeated raw path, a raw path name with a
  character no Windows file name holds (`? * " < > |` or U+0000 to U+001F) or with
  U+007F (refused as in output names), a raw
  path that can never verify (another entry's folder, or 4096 UTF-8 bytes or more,
  which no Linux path call opens), a raw path name refused on every host (over 255
  UTF-8 bytes, or not valid UTF-8: a lone surrogate), an entry that exists but is not
  a regular file, a hash mismatch) as
  `rejected` (exit 2). The manifest's own entries are checked before the snapshot
  is looked at, so a bad manifest is rejected even when the snapshot is missing. It never ends with a traceback.
- **W4** The evidence uploads in `audit-runtime.yml` keep names that start with a
  dot but never take a collection's unfinished snapshot (`.collect-*` beside the
  destination), which a host process killed during collection leaves behind and
  which was never checked as a whole. Checked in `test_host_safety.WorkflowTests`.
- **W5** The semantic output gate hashes every file of the workflow output (a PNG
  figure only has to exist and be nonempty; folders count only through the files
  they hold) or fails:
  a symbolic link (also one to a folder, or a dangling one), a FIFO or other special
  file, or a folder it cannot list fails the gate with a reason that names it, so
  two outputs that differ only in such an entry never pass as repeatable. A listing
  failure also gives the operating system's cause, so an output folder the workflow
  never created does not read as a permission problem. Checked in
  `runner_workload.semantic_manifest`.

## Deliberate behaviour differences from the Linux-only runner (PR #32)

- Source files are staged from Git's object store, not from the checked-out files,
  so a checkout whose files differ from the commit (CRLF line ends from Git on
  Windows, or local edits) still stages exactly the committed bytes.
- Source paths and output names that Windows or an artifact zip would read
  differently are refused on every host: reserved device names (`CON`, `NUL`,
  `COM1`...), names ending in a dot or space, `\ / : * ? " < > |`, control
  characters (U+0000 to U+001F, and U+007F, which Windows allows but is refused to
  be strict), non-UTF-8 names, names shaped like an
  NTFS short name (`PROGRA~1`), and source paths that clash when case is ignored.
- Source paths that enter Git's own folder (`.git` in any case, or `GIT~1`) are
  refused before anything is written. PR #32 failed later on such a commit, when
  the checked-out bytes did not match.
- The staged copy's index is built with no inherited `GIT_*` variables, no
  system or global Git configuration, no file system monitor and an empty hooks
  folder. Git before 2.32 cannot leave out the global configuration, so it is
  refused before staging.
- A Docker daemon that cannot be reached, or does not report Linux containers,
  gives a `blocked` result (exit 2) before any source is read.
- The audit container gets no proxy setting from the host's Docker CLI
  configuration: the run sets every proxy variable that the CLI would copy from the
  `proxies` of its `config.json` (HTTP, HTTPS, FTP, ALL and NO_PROXY, in upper and
  lower case) to an empty value. PR #32 left FTP_PROXY out, so a proxy URL, which can
  hold a password, reached the audited code and could be written to its output.
- `git`, `uv` and `docker` are run only from absolute `PATH` folders, never from the
  current folder or a relative `PATH` entry (Windows searches the current folder
  first), so a program committed in the audited checkout cannot run on the host.
- `--source` may name a subfolder of the checkout, or a linked worktree; the whole
  commit is staged, with objects read from the repository's common Git folder.
- Only the objects the audited commit reaches are staged, packed by Git. PR #32
  copied every loose object and pack of the source's store, so a stash (with `-u`,
  untracked files such as `.env`), an unpushed branch or a blob once added and never
  committed was readable by the audited code under `/input/.git`.
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
- Every host program but the container run (`run_bounded`, which reads the log on a
  thread with its own deadline) runs with captured output through `run_captured`,
  which kills it at its timeout and returns at once. `subprocess.run` on Windows
  reads the pipes to their end after the kill, so a child that a launcher started
  (Git for Windows' `cmd\git.exe`, a Docker CLI plugin such as buildx) kept it
  waiting.
- `verify_snapshot` refuses raw paths with `\` or `:` in any part on every host;
  on Windows such a path would name a drive, a share or a stream. It also refuses
  `* ? " < > |` and U+0000 to U+001F on every host, as output names are: no Windows
  file can have such a name, and Windows reads one as absent, so PR #32 reported it
  as blocked there with every file in place. U+007F, which Windows allows, is
  refused too, as in output names.
- `verify_snapshot` also refuses a raw path name that is not valid UTF-8 (a lone
  surrogate in the manifest, such as `\udcff`), as source paths and output names are
  refused. PR #32 verified such a name on Linux, where Python reads U+DC80-U+DCFF as
  a non-UTF-8 byte (`raw/\udcff.json` named the file `raw/<0xFF>.json`); NTFS allows
  a lone surrogate too.
- The semantic output gate fails on a symbolic link, a special file or a folder it
  cannot list (W5); PR #32 skipped them, so two outputs differing only there passed
  as repeatable. It walks the output with its own stack: PR #32's `rglob` recursed
  on Python 3.11, so an output nested about 1,000 folders deep raised
  RecursionError past the gate's handler and crashed the workload.
