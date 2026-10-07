# Checkpoint reviews

One report per [checkpoint review](../../RAPID_DEVELOPMENT.md#11-step-back-between-milestones), named `<YYYY-MM-DD>-<milestone>.md` (for example `2026-10-08-m3.md`). Keep each report short; detailed fixes live in pull requests and [TODO.md](../../TODO.md).

## Report outline

1. **Scope:** base and head commits (previous checkpoint tag to `main`), reviewer, review levels, and the workflow replay compared.
2. **Findings:** one line each with its TODO `REVIEW-xx` id, *blocking* or *later*, and its outcome (fixed, or kept with a checked reason).
3. **Escapes log:** each defect that reached `main` or a ready pull request since the last checkpoint, the step that should have caught it, and who did.
4. **Decisions:** one line each with its reason, so later work does not reopen them.
5. **Guideline changes:** rules added because of escapes, and rules removed or reworded because nobody follows them.
6. **Exit:** blocking findings merged, tag set, README/ROADMAP/TODO reconciled, and the next milestone's plan agreed (or the reason the checkpoint was skipped).
