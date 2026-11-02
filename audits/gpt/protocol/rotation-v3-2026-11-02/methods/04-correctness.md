#### 4. Examine correctness and failure behavior

Review public interfaces and their callers, not just individual functions.

- Check empty, singleton, small-sample and large inputs; duplicate keys; ties; unordered records; malformed metadata; invalid enum values; nulls; NaN; infinity; overflow; impossible prices or volumes; and numerical boundary conditions.

- Follow error and partial-failure paths. Verify invalid inputs are rejected before expensive work or persistent side effects where the contract requires that.

- Test output-directory reuse, stale artifacts, interrupted writes, disk/permission failures, atomic publication, locking and concurrent access where supported. Use only temporary resources.

- Examine mutable caches, global state, nondeterministic ordering, seeds, cross-run contamination and resource cleanup.

- Inspect Linux/Windows portability, paths, encoding, case sensitivity, line endings, symlinks and subprocess handling. Separate executed platform checks from static portability review.

- Inventory portability risks per file: text I/O without explicit encoding, rename semantics, literal interpreter commands instead of `sys.executable`, CSV line endings, hard-coded temporary directories and unguarded POSIX-only modules. Recheck previously tracked items and report only new or materially changed instances as new findings. A pattern match is a lead, not proof of incorrect behavior.

- Review expression parsing, deserialization, filesystem access, subprocesses, dependency handling and workflow permissions where relevant. Cite current authoritative advisories before calling a dependency vulnerability verified; without access, mark vulnerability status unverified.

- Distinguish guaranteed supported behavior from deliberately unsupported capabilities. Recommend expanding scope only when the benefit justifies its cost.

