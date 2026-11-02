# Audit runner contract (host side)

These rules hold on Linux and Windows hosts. The container side always runs Linux.
`contract.py` checks each rule while `CONTRACT_CHECKS=1`; every test suite and the
CI host-test steps set it, production runs do not. A failed check raises
`ContractViolation` (an `AssertionError`), never an ordinary rejection.

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
  whose size and times may lag the open handle's. On POSIX every folder is reached
  through no-follow directory descriptors. On Windows each path component is
  checked to be no reparse point just before the open, and each folder again after
  it was listed; a concurrent writer is excluded by P1. Checked in `read_opened`.
- **I2** On POSIX, where both walks run, the descriptor walk and the path walk give
  the same outcome, records and summaries for the same unchanging tree. Checked
  after every collection with the descriptor walk, except a rejection for a change
  during the walk (only tests can cause one, since P1 excludes a writer).

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
  folder.
- A Docker daemon that does not report Linux containers gives a `blocked` result
  (exit 2) before any source is read.
- The CA bundle for the image build comes from the system bundle, else Python's
  default CA file, else (Windows) the certificate store exported as PEM.
- On a Windows host the container's outside-file and host-process probes are not
  run, so `boundary.json` lacks `outside_fixture_absent` and
  `host_process_not_visible`: a Windows path or process ID names nothing inside the
  Linux container, so both checks would pass whatever leaked.
