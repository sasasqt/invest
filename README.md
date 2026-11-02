# GPT repository-audit archive

This is the independent audit-output branch `gpt/repo-audits` for [sasasqt/invest](https://github.com/sasasqt/invest). Product source and its normal history remain on [main](https://github.com/sasasqt/invest/tree/main).

Every commit in this branch's rewritten ancestry contains only `audits/gpt/` and, in later snapshots, this audit-navigation README. The root has no parents. The inherited product snapshot and its main ancestry have been removed from this branch; no backup ref was created. Fourteen audit snapshots were replayed with their audit contents intact.

- [Findings](audits/gpt/findings.md), [recommendations](audits/gpt/recommendations.md), [coverage](audits/gpt/coverage-map.md) and [peer cross-check](audits/gpt/cross-check.md).
- [Maintained state](audits/gpt/state.json) and [checkpoint](audits/gpt/checkpoint.json).
- [Detailed-method index](audits/gpt/protocol/rotation-v3-2026-11-02/index.json), pinned by the active dispatcher to an immutable commit and verified hashes.
- [History rewrite and evidence](audits/gpt/2026-11-02-history-rewrite.md), including the [old-to-new audit commit map](audits/gpt/history-rewrite-2026-11-02/commit-map.json).

Historical reports, state and evidence retain original commit IDs as provenance. To open an old own-audit reference, use the commit map's replacement ID and the same file path. Product-source and runner SHAs are not translated. Each audit independently pins fresh source; product paths and unread ranges belong to that source commit, not to this archive.

Normal publication changes only `audits/gpt/` and preserves this README. It uses single-parent non-forced updates, never merges/rebases main into this archive, and never recreates removed source ancestry. The user-authorized history rewrite is a one-off exception. Historical cleanup reports describe their original state; this rewrite supersedes their statements about retaining source ancestry and restoring source files.

The seven-field rotation, 120-minute plan, 03:00 audit and 21:00 PR review remain unchanged in Europe/Berlin. The unresolved runner blocker INV-PR32-001 remains; this migration executes no product code or unsafe runner workflow.
