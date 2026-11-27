# Proposal: docs-audit skill v3.3

Draft for review, written 2026-11-20. **Nothing is decided.** The weekly docs audit follows a skill file in the project library, outside Git (see [Docs audit](../CLAUDE_WORKFLOW.md#docs-audit-saturdays)), so ChatGPT's open-PR review cannot see it. This draft pull request puts the live version, the proposed version and the diff between them in the repository so that ChatGPT can review the change before the user decides. It is not meant to be merged: once the user decides, it is closed, unless the user wants it kept as a record.

## 1. Today

- The docs audit runs every Saturday at 05:00 Berlin, reports only, and changes nothing. Its findings go to the docs-audit ledger; the daily bug fix fixes the rows whose Area is `repo`.
- The live skill is v3.2.1 since 2026-11-20 20:54 UTC ([SKILL.v3.2.1.md](2026-11-20-docs-audit-v3.3/SKILL.v3.2.1.md)): v3.2 plus a hotfix, so that an empty `workflow_sources` map in its state file counts as a first run and the workflow page gets its first full comparison.
- Its step 3b checks, for each pull request merged since the last run, that the pull request's TODO item is ticked and that the README and ROADMAP lines it made wrong were changed. It does not search for other passages that name what the pull request touched.

## 2. What v3.3 changes

The full proposed text is [SKILL.v3.3.md](2026-11-20-docs-audit-v3.3/SKILL.v3.3.md); the change against the live version is [v3.2.1-to-v3.3.diff](2026-11-20-docs-audit-v3.3/v3.2.1-to-v3.3.diff) (7 hunks).

| Where | v3.2.1 | v3.3 |
|---|---|---|
| Step 3b | ticked TODO item, plus the README and ROADMAP lines the pull request made wrong | also lists everything the pull request touched (files, modules, functions, commands and options, configuration keys, output fields, TODO ids, milestones; from `git show --stat=200` and its diff), searches the repository's Markdown on `main` for each name in every spelling the docs use for it (a subcommand with and without its program, a module as path, file name and dotted name, a TODO id also by its prefix, to find ranges such as `REVIEW-12 to REVIEW-17`) and checks every passage found. At most about 20 passages per name and about 10 minutes in all; the unread passages (each as `path:line` with the commit searched and the line's text), the names left out and the pull requests not searched are listed under Health, and the next run works through that list first: it checks every passage of the name, in any file, that starts with the saved text, and every one on a line the diff since that commit adds, which together cover every place the passage can have moved to; an item stays listed until it has been checked |
| Time budget | about 60 minutes, 25 of them reading | about 75 minutes, 40 of them reading (10 for step 3b's searches, 10 for step 3i); the full-read rotation is still cut first |
| Step 1.1 | one `git fetch` for both audit branches | one `git fetch` per branch, so a missing branch does not stop the other |
| Step 2l | pattern `once [a-z ]+ exists`; says nothing about hits an earlier run found consistent | pattern `exists?` (also finds "once those tools exist"); every hit is checked again each run, because a sentence goes stale when the work it calls planned lands; the still-consistent hits are listed in one line; calibration updated (16 hits, 5 stale on `main` eb64ad8) |
| Step 3i | does not say what a missing `full_reads` key means (the live `state.json` has none yet); `TODO.md` is read like any other file | a missing key is an empty map; skips the dated records under `runs/` and `docs/reviews/`, the mirrors under `docs/audits/`, and `TODO.md` (checked item by item in step 3a); a file over 40 KB is that run's only file; says how it differs from step 1's orientation read |
| Report | "Quiet week" whenever nothing is new | the summary's third line by case: "Quiet week" only with no new findings and nothing skipped, cut or left unread; "Nothing new in what was checked; see Health for what was not" with no new findings but something skipped, cut or left unread; "Not every source was checked in full; see Health" with new findings and something skipped, cut or left unread; no third line otherwise |
| Step 6 (`state.json`) | step 3i's files get today's date | only files read to their end get today's date; a file read in part keeps its old date |

## 3. Why

- On 2026-11-20 the user approved one general rule for authors and the audit: when a change touches something, re-read every doc passage that names it. The author side is step 8 of [Before marking ready](../../GIT_GUIDELINES.md#before-marking-ready), added by pull request #67; step 3b is the audit side, for what slipped through.
- The case that started it: README.md:5 and :180 still describe REVIEW-15 to REVIEW-17 as open, although pull requests #27, #39 and #40 ticked them. Those pull requests edited other README lines, so the audit's check of the lines a pull request edited could not find these.

## 4. How it was reviewed so far

Eight [hardening rounds](../../GIT_GUIDELINES.md#hardening-rounds) on 2026-11-20, together with pull requests #65 and #67, each with two Opus 5.5 reviewers at xhigh effort. Every finding was fixed with a check that fails before its fix and passes after. Findings in this skill: round 1, the empty-map bug (now the live hotfix); round 2, step 3b left out `audits/`; round 3, a time cut could hide a partly searched pull request; round 5, the search command failed for names that start with `-`; rounds 6 to 8, spellings the search missed and the 20-passage cap. Rounds 6, 7 and 8 found only low issues, so the rounds stopped by the requester's stop rule.

ChatGPT review 1 (2026-11-21, on this pull request's first head, d94db13): one medium finding, INV-PR71-001. Step 3b's cap reported only how many passages of a busy name were left unread, and the carry-over named only unsearched pull requests and left-out names, so the next run could check the same 20 passages again and never reach the others. Fixed in this pull request's second commit: Health lists each unread passage as `path:line`, the next run works through that list first, and an item stays listed until it has been checked. The check `check_gpt1-rules-1.sh` in the project library fails on the first head's skill text and passes on this one.

ChatGPT reviews 2, 3 and 4 (2026-11-22 to 2026-11-24, on the second head, ad7b0dd): no blocking issues.

ChatGPT review 5 (2026-11-25, same head): one medium finding, INV-PR71-002, and one optional point. A carried-over passage kept only its name and `path:line`, so after a line was added above two passages of the same name, the next run could check the one already checked and drop the unread one. And the summary said "Nothing new in what was checked" also when there were new findings. Fixed in this pull request's third commit: each unread passage is listed with the commit searched and its line's text; the next run checks the passages that start with that text and those on lines the diff since that commit adds, checks every passage of the name in the file when none starts with it, and looks in other files before closing one whose file is gone; the summary's third line has one text per case. A blind second review of the first version of this fix found three more low gaps (two lines sharing their first 80 characters, a renamed and rewritten file, and which commit and text to save), all fixed in the same commit. Three checks in the project library (`hardening-checks/gpt-2/`, one of them a simulation with eight fixtures) fail on the second head's skill text and pass on the third.

ChatGPT review 6 (2026-11-27, on the third head, f96a0d3): INV-PR71-002 only partly resolved. The rule looked for a listed passage in its own file first and in other files only when that file was gone or no longer named it, so a passage moved and rewritten into another file was lost while a checked passage stayed behind. Fixed in this pull request's fourth commit by one rule that is complete by construction instead of one more case: the next run checks every passage of the name, in any file, whose line starts with the saved text (read from the saved commit, not copied from the report), and every passage of the name on a line that the diff since that commit adds over the searched Markdown. An unchanged passage still starts with its saved text wherever it moved; an edited or moved one is a line that diff adds; so when there are none, the passage is gone. A TODO id's prefix lines that span it count as its passages, a commit that is no longer an ancestor of `main` sends the name back to a fresh search, and passages left unread are listed again with today's commit and text. A blind second review applied the rule with real git to throwaway repositories (renames with and without edits, a rewrite git does not see as a rename, whitespace changes, a line split and two joined, line-ending changes, a merge, and ChatGPT's case) and found the passage, or rightly closed it, in every case; its four low points are in the same commit. Two checks (`hardening-checks/gpt-3/`, a wording check that five deliberately broken copies of the text fail, and a simulation with ten fixtures) fail on the third head's text and pass on this one; the earlier skill checks still pass, except the two gpt-2 checks they replace.

## 5. Going live

- **Before:** two clean ChatGPT reviews of this pull request's head; pull request #67 merged, so that step 3b mirrors a rule that is on `main`; pull request #65 merged, because v3.3's text cites it (step 3i) and the GIT_GUIDELINES.md:58 fix (step 2l's calibration).
- **Install:** keep v3.2.1 as `SKILL.v3.2.1.md` in the library, copy v3.3 over `SKILL.md`, compare the two byte for byte. Then a small pull request changes the docs-audit version named in docs/CLAUDE_WORKFLOW.md to v3.3. Target: before the run of Saturday 2026-12-05, 05:00 Berlin (the run of 2026-11-28 comes before two clean reviews of the fourth head are possible).
- **Undo:** copy `SKILL.v3.2.1.md` back over `SKILL.md`.

## 6. Questions for reviewers

1. Does step 3b's search find every passage a merged pull request can make wrong, for the spellings this repository's docs use? Name any spelling it misses.
2. Are the cap of about 20 passages per name and the 10 minutes enough in a busy week, and does the carry-over to the next run lose anything?
3. Can a time cut, the cap or a skipped source still let the report say "Quiet week"?
4. Does step 6's `full_reads` rule date a file correctly when step 3i stops partway?
5. Does anything in v3.3 contradict the [Docs audit](../CLAUDE_WORKFLOW.md#docs-audit-saturdays) section of the workflow page, or author step 8 as pull request #67 writes it?
