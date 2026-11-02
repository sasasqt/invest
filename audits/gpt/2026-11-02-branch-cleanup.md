# In-place audit-branch cleanup — 2 November 2026

The user authorized applying the audit-only layout in place while retaining `gpt/repo-audits`. The prepared commit has parent `18a3bb690ec92263f6c714ebb19ce333983b4683` and retains all earlier history. It removes 109 inherited product/configuration/saved-result files and replaces the inherited product README with audit navigation. These 110 entries all matched their original source snapshot. The current tree is README plus audits/gpt; source paths remain resolvable at their recorded source commits and in retained history.

All 170 existing audit files remain present. Four detailed-protocol/index/template files are updated; the other 166 keep identical Git blob IDs and modes, including state.json, checkpoint.json, queues, findings, coverage, benchmark and research histories, reports, evidence, and runner tools. Only the source-selection description and publication/bootstrap rules change; rotation, budget, data restrictions, independent-review rules and runner-security blocker remain.

Normal publication still changes only audits/gpt. The root README is read-only to the routine. A missing branch is now an explicit publication gap; normal audits cannot recreate inherited source from main. Fresh source, output, protocol and runner revisions remain distinct.

The latest scheduler run was recorded completed before preparation. Its published state at the parent above is retained, rather than the older activation snapshot. Publication uses a freshly reread parent, a single-parent commit, force=false, and an expected-head check. Branch movement requires reconciliation and rebuilding; do not overwrite concurrent progress.

The active dispatcher will pin this commit's updated method index, SHA-256 `3971f1368371353c060884292e0e2cc199abd1ee82f538d6d73dc725f1ad0606`, and its module hashes. The preceding immutable methods remain available at `40187531fedd04c2fc8be5a049874cd49b0b6cee`. [Preservation manifest](2026-11-02-branch-cleanup/manifest.json) and [prepublication checks](2026-11-02-branch-cleanup/acceptance.json) record the exact scope. Remote reachability and parent-to-commit tree comparison must be verified after the update before reporting success.

No product imports/tests/builds, runner workflow, historical replay, paid workload or additional audit run is part of this migration. Existing runtime validation remains blocked by INV-PR32-001 until independently resolved. Main, the runner-development branch, peer output and the PR-review routine are outside this write.

Rollback uses a new commit on the then-current output head, restoring only the original out-of-folder entries by the manifest's Git object IDs and the old README, while preserving subsequent audit updates. Restore the previous dispatcher/protocol pin if reverting its rules. Never reset or force-push. No backup branch is necessary because every original commit remains reachable through the retained parent chain.
