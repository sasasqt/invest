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
  every host. Always enforced for the bytes read from Git; checked again on the
  written file in `stage_source`.
- **Q5** Host-side uv runs with `--no-config`. Checked in `host_uv`.

## Invariants

- **I1** The host reads bytes only from an output entry whose own `lstat` showed a
  one-link regular file and whose opened descriptor has the same identity. On POSIX
  every folder is reached through no-follow directory descriptors. On Windows each
  path component is checked to be no reparse point just before the open, and each
  folder again after it was listed; a concurrent writer is excluded by P1. Checked
  in `read_opened`.
- **I2** On POSIX, where both walks run, the descriptor walk and the path walk give
  the same outcome, records and summaries for the same tree. Checked after every
  collection with the descriptor walk.

## Deliberate behaviour differences from the Linux-only runner (PR #32)

- Source files are staged from Git's object store, not from the checked-out files,
  so a checkout whose files differ from the commit (CRLF line ends from Git on
  Windows, or local edits) still stages exactly the committed bytes.
- Source paths and output names that Windows or an artifact zip would read
  differently are refused on every host: reserved device names (`CON`, `NUL`,
  `COM1`...), names ending in a dot or space, `\ / : * ? " < > |`, control
  characters, non-UTF-8 names, and source paths that differ only by case.
