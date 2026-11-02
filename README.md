# GPT repository-audit archive

This is the audit-output branch `gpt/repo-audits` for [sasasqt/invest](https://github.com/sasasqt/invest). Product source is on [main](https://github.com/sasasqt/invest/tree/main).

The current tree contains audit reports, cumulative state, detailed methods, evidence and supporting tools under [`audits/gpt/`](audits/gpt/), plus this read-only navigation file. Each audit independently fetches and pins the source commit it examines. Product paths recorded in reports and checkpoints belong to that pinned source, not to this archive's tree.

- [Findings](audits/gpt/findings.md), [recommendations](audits/gpt/recommendations.md), [coverage](audits/gpt/coverage-map.md) and [peer cross-check](audits/gpt/cross-check.md).
- [Maintained state](audits/gpt/state.json) and [checkpoint](audits/gpt/checkpoint.json).
- [Detailed-method index](audits/gpt/protocol/rotation-v3-2026-11-02/index.json). The active dispatcher pins an immutable commit and verifies its method hashes.
- [Layout migration, preservation evidence and rollback procedure](audits/gpt/2026-11-02-branch-cleanup.md).

This branch retains its original source ancestry and all prior audit commits. The 2026-11-02 cleanup removed inherited source from the current tree through a normal single-parent commit. No history rewrite, force-push, source synchronization, product fix or audit-completion claim is implied.

Normal audit publication changes only `audits/gpt/` and preserves this README. Do not merge or rebase main into this branch, restore the old source snapshot, or use this archive as a product checkout. Runner tooling requires its own verified execution boundary; the unresolved INV-PR32-001 blocker remains in force. Runtime workflow development remains separate in PR #32.

The audit's seven-field rotation and planned 120-minute budget remain unchanged, as do the 03:00 audit and 21:00 PR-review schedules in Europe/Berlin.
