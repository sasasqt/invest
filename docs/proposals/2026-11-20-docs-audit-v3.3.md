# Proposal: docs-audit skill v3.3

Draft for review, written 2026-11-20. **Nothing is decided.** The weekly docs audit follows a skill file in the project library, outside Git (see [Docs audit](../CLAUDE_WORKFLOW.md#docs-audit-saturdays)), so ChatGPT's open-PR review cannot see it. This draft pull request puts the live version, the proposed version and the diff between them in the repository so that ChatGPT can review the change before the user decides. It is not meant to be merged: once the user decides, it is closed, unless the user wants it kept as a record.

## 1. Today

- The docs audit runs every Saturday at 05:00 Berlin, reports only, and changes nothing. Its findings go to the docs-audit ledger; the daily bug fix fixes the rows whose Area is `repo`.
- The live skill is v3.2.1 since 2026-11-20 20:54 UTC ([SKILL.v3.2.1.md](2026-11-20-docs-audit-v3.3/SKILL.v3.2.1.md)): v3.2 plus a hotfix, so that an empty `workflow_sources` map in its state file counts as a first run and the workflow page gets its first full comparison.
- Its step 3b checks, for each pull request merged since the last run, that the pull request's TODO item is ticked and that the README and ROADMAP lines it made wrong were changed. It does not search for other passages that name what the pull request touched.

## 2. What v3.3 changes

The full proposed text is [SKILL.v3.3.md](2026-11-20-docs-audit-v3.3/SKILL.v3.3.md); the change against the live version is [v3.2.1-to-v3.3.diff](2026-11-20-docs-audit-v3.3/v3.2.1-to-v3.3.diff) (6 hunks).

| Where | v3.2.1 | v3.3 |
|---|---|---|
| Step 3b | ticked TODO item, plus the README and ROADMAP lines the pull request made wrong | also lists everything the pull request touched (files, modules, functions, commands and options, configuration keys, output fields, TODO ids, milestones; from `git show --stat=200` and its diff), searches the repository's Markdown on `main` for each name in every spelling the docs use for it (a subcommand with and without its program, a module as path, file name and dotted name, a TODO id also by its prefix, to find ranges such as `REVIEW-12 to REVIEW-17`) and checks every passage found. At most about 20 passages per name and about 10 minutes in all; what is left out is listed under Health and searched first by the next run |
| Time budget | about 60 minutes, 25 of them reading | about 75 minutes, 40 of them reading (10 for step 3b's searches, 10 for step 3i); the full-read rotation is still cut first |
| Step 1.1 | one `git fetch` for both audit branches | one `git fetch` per branch, so a missing branch does not stop the other |
| Step 2l | pattern `once [a-z ]+ exists`; says nothing about hits an earlier run found consistent | pattern `exists?` (also finds "once those tools exist"); every hit is checked again each run, because a sentence goes stale when the work it calls planned lands; the still-consistent hits are listed in one line; calibration updated (16 hits, 5 stale on `main` eb64ad8) |
| Step 3i | does not say what a missing `full_reads` key means (the live `state.json` has none yet); `TODO.md` is read like any other file | a missing key is an empty map; skips the dated records under `runs/` and `docs/reviews/`, the mirrors under `docs/audits/`, and `TODO.md` (checked item by item in step 3a); a file over 40 KB is that run's only file; says how it differs from step 1's orientation read |
| Report | "Quiet week" whenever nothing is new | "Quiet week" only when Health lists nothing cut or left unread; otherwise "Nothing new in what was checked; see Health for what was not" |
| Step 6 (`state.json`) | step 3i's files get today's date | only files read to their end get today's date; a file read in part keeps its old date |

## 3. Why

- On 2026-11-20 the user approved one general rule for authors and the audit: when a change touches something, re-read every doc passage that names it. The author side is step 8 of [Before marking ready](../../GIT_GUIDELINES.md#before-marking-ready), added by pull request #67; step 3b is the audit side, for what slipped through.
- The case that started it: README.md:5 and :180 still describe REVIEW-15 to REVIEW-17 as open, although pull requests #27, #39 and #40 ticked them. Those pull requests edited other README lines, so the audit's check of the lines a pull request edited could not find these.

## 4. How it was reviewed so far

Eight [hardening rounds](../../GIT_GUIDELINES.md#hardening-rounds) on 2026-11-20, together with pull requests #65 and #67, each with two Opus 5.5 reviewers at xhigh effort. Every finding was fixed with a check that fails before its fix and passes after. Findings in this skill: round 1, the empty-map bug (now the live hotfix); round 2, step 3b left out `audits/`; round 3, a time cut could hide a partly searched pull request; round 5, the search command failed for names that start with `-`; rounds 6 to 8, spellings the search missed and the 20-passage cap. Rounds 6, 7 and 8 found only low issues, so the rounds stopped by the requester's stop rule. ChatGPT has not reviewed the skill yet.

## 5. Going live

- **Before:** two clean ChatGPT reviews of this pull request's head; pull request #67 merged, so that step 3b mirrors a rule that is on `main`; pull request #65 merged, because v3.3's text cites it (step 3i) and the GIT_GUIDELINES.md:58 fix (step 2l's calibration).
- **Install:** keep v3.2.1 as `SKILL.v3.2.1.md` in the library, copy v3.3 over `SKILL.md`, compare the two byte for byte. Then a small pull request changes the docs-audit version named in docs/CLAUDE_WORKFLOW.md to v3.3. Target: before the run of Saturday 2026-11-28, 05:00 Berlin.
- **Undo:** copy `SKILL.v3.2.1.md` back over `SKILL.md`.

## 6. Questions for reviewers

1. Does step 3b's search find every passage a merged pull request can make wrong, for the spellings this repository's docs use? Name any spelling it misses.
2. Are the cap of about 20 passages per name and the 10 minutes enough in a busy week, and does the carry-over to the next run lose anything?
3. Can a time cut, the cap or a skipped source still let the report say "Quiet week"?
4. Does step 6's `full_reads` rule date a file correctly when step 3i stops partway?
5. Does anything in v3.3 contradict the [Docs audit](../CLAUDE_WORKFLOW.md#docs-audit-saturdays) section of the workflow page, or author step 8 as pull request #67 writes it?
