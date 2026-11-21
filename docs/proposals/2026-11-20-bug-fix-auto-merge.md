# Proposal: may the daily bug fix merge its own pull requests?

Draft for review, written 2026-11-20 and revised 2026-11-21 after ChatGPT's first review (section 7). **Nothing is decided.** The user picks one of the options below; until then the bug fix never merges and nothing on `main`, in the routine or in the repository settings changes. This file is in a draft pull request so that the ChatGPT open-PR review can check the options before the user picks one.

## 1. The rule today

- [README.md](../../README.md#development-guidelines) (Development guidelines): "nothing merges into `main` without the user's word."
- [docs/CLAUDE_WORKFLOW.md](../CLAUDE_WORKFLOW.md#bug-fix-daily), bug fix: "**Never merges.** It never merges, pushes to `main`, approves, enables auto-merge, or closes or reopens a pull request, and never force-pushes"; [merge gate](../CLAUDE_WORKFLOW.md#merge-gate): "the scheduled bug fix never merges."
- The bug-fix skill in the project library (version 15.3), first hard limit: "**Never merge.** Do not merge or squash any pull request, push to `main`, approve, enable auto-merge, or close or reopen pull requests."
- The routine's prompt (version 13), constraint 4: "Never merge into main. Never push to main, approve, enable auto-merge, or close or reopen a pull request."
- The user set this constraint on 2026-10-25 ("never merge into main"). Allowing merges reverses it, so it needs the user's explicit yes.
- In practice, merges happen in batches: the user tells a Claude thread to "merge the safe ones in best order" (2026-11-11, 11-14 and 11-18). That thread calls a pull request **safe** when CI is green on every job and ChatGPT's review is clean on the current head. A head pushed after ChatGPT's last review waits for its next pass.
- [GIT_GUIDELINES.md](../../GIT_GUIDELINES.md#pull-requests-and-checks) recommends a protected `main` with required checks. `main` has no branch protection today. CI runs on each push to a pull request and on each push to `main`, but it does not run again when `main` moves under an open pull request.

## 2. Evidence

Bug-fix pull requests are the ones from branches `claude/project-thread-7rf56w-*`, checked on 2026-11-20.

| Question | Answer |
|---|---|
| How many merged, closed, open | 14 merged (#30, #31, #33, #34, #35, #38, #41, #48, #50, #51, #53, #56, #58, #60), none closed without merging, 4 open (#57, #59, #63, #64) |
| Days from opening to merge | median 3.2, mean 4.6, longest 10.3 (#33) |
| Defects ChatGPT found after the routine's own review ladder | 3 of the 14: [#33](https://github.com/sasasqt/invest/pull/33) (a CSV with mixed time-zone offsets was published in part instead of refused), [#41](https://github.com/sasasqt/invest/pull/41) (bundle hashes checked on one read, scores computed from a second read), [#51](https://github.com/sasasqt/invest/pull/51) (the as-traded check ran before the ledger guard, so a refused formula told one bit about reserved rows; the fix asks the ledger first). Plus a TODO.md merge conflict on [#53](https://github.com/sasasqt/invest/pull/53). All four were fixed before merging |
| Defects that reached `main` | none: no row of the bug-hunt ledger traces a code defect to a merged bug-fix pull request. One low row says these pull requests left README and ROADMAP's open-defect lists stale |
| What waiting cost | the runs of 2026-11-09, 11-10 and 11-11 opened nothing, because five of the routine's pull requests were open (its cap), all green and waiting only for a merge. The 2026-11-07 run could not open a finished fix because it overlapped the unmerged #34 |
| When ChatGPT reviews | every day at 21:00 Berlin ([GPT / OpenAI routines](../GPT_OPENAI_ROUTINES.md)). It keeps one maintained comment per pull request. Each substantive round leaves the marker `<!-- invest-pr-review-round:v1 pr=N head=SHA target=SHA run=ID -->` there, and a clean result adds a short notice with `<!-- invest-clean-review:v1 ... -->`, which ChatGPT itself counts as zero extra rounds. Since 2026-11-21 a pass over an unchanged head runs a fresh substantive round (#63: "substantive round 2 on this revision" on head 8821858); up to 2026-11-20 it reused the first review |
| When the bug fix runs | every day at 04:00 Berlin; a new pull request opens at about 05:00 |

What the evidence says: the routine's own ladder let about one pull request in five through with a real defect, and the ladder plus ChatGPT let none through. Any merge by the routine must therefore wait for ChatGPT. The user asks for **two** ChatGPT confirmations. ChatGPT's review behaviour changed on 2026-11-21: its pass that day on #63 ran a second substantive round on an unchanged head, where the passes up to 2026-11-20 reused the first review and added only a notice. Two confirmations therefore take two passes, about two days.

Risks specific to this repository:

1. **Stale CI and a merge race.** Without protection, a squash merge goes through even when `main` moved after the last CI run. The merge call's expected SHA pins the pull request's head, not `main`, so reading `main` once more right before the call cannot close the gap: only a ruleset on `main` that requires the checks and an up-to-date branch does.
2. **TODO.md and README conflicts.** Almost every bug-fix pull request adds REVIEW items. Each merge pushes a conflict onto the other open pull requests, and resolving it resets their CI and their ChatGPT review.
3. **One GitHub account.** ChatGPT, every Claude session and the user all write as `sasasqt`. A comment proves nothing about its author, and a marker can be copied; only the marker's head, target and run id can be checked against ChatGPT's own dated history in its maintained comment. A separate GitHub account for the ChatGPT routine would make the author a hard check. A merge by the routine also shows as the user's.
4. **Decisions inside fixes.** Some fixes carry the user's design calls. High-severity fixes change results the most.
5. **Undo.** A bad merge is undone by a revert pull request. That is easy for one squash commit and harder once later merges build on it.

## 3. Options

| | Option | What merges without the user | Effect |
|---|---|---|---|
| A | **Gated auto-merge, no high fixes** (recommended) | at most one bug-fix pull request per run that passes every gate in section 4 | about 2 days from opening to merge while `main` stays still; each merge moves `main`, so the other pull requests then need two fresh passes: about one merge every two days in all, which slows the cap stalls rather than ending them |
| B | Auto-merge mirrors, coverage and typing only | generated mirrors, tests-only and types-only pull requests, under the same gates | coverage and typing keep growing; the cap of five is unchanged, because those never count toward it |
| C | Daily one-tap merge card | nothing; after ChatGPT's pass, the routine posts one card listing the pull requests that pass the gates, and the user's one tap lets a thread merge them in order | about 1 to 2 days if the user taps daily; the rule stays as it is |
| D | Keep it manual | nothing | as today |

## 4. Gates (options A and B; option C uses them to build its list)

All must hold at merge time. If one fails, nothing merges and the run's report says which gate failed.

1. **Which pull requests.** Opened by this routine. Ready for review, not a draft. No `hold` label. Under A: fix pull requests whose fixed rows are all low or medium, docs-only pull requests, mirrors, coverage and typing. Under B: mirrors, coverage and typing only.
2. **Exclusions.** Any fixed row rated high. "Checkpoint due". A question still waiting in the body. Changes under `.github/`, to dependencies or `uv.lock`, or to the rule text of GIT_GUIDELINES.md, PYTHON_GUIDELINES.md, CI_CD_GUIDELINES.md, DESIGN_BY_CONTRACT.md, RAPID_DEVELOPMENT.md or README's Development guidelines.
3. **Own reviews.** The ladder rounds and reviewer 2's checks are in the body with every finding resolved, and no review comment is unanswered.
4. **Two ChatGPT confirmations, bound to head and target.** Two substantive ChatGPT rounds that both found no blocking issue, read from the `invest-pr-review-round:v1` markers in ChatGPT's one maintained comment on the pull request: two distinct `run` ids on two different dates, each with `head` equal to the current head and `target` equal to the current `main`, and the maintained comment's current heading "No blocking issues found". A clean notice (`invest-clean-review`) counts as zero rounds, and so does any comment without a round marker. A new head or a new `main` starts the count again; there is no exemption for a conflict-free merge of `main`, because two reviews of the old `main` say nothing about the new integration. Limit: every writer uses the same GitHub account, so a marker cannot prove who wrote it; the run ids are matched against the dated history ChatGPT keeps in that comment, the report quotes them, and a separate GitHub account for the ChatGPT routine would turn the author into a hard check.
5. **Protection on `main`, checked before each merge.** The routine reads the rules in force for `main` (GitHub's branch rules endpoint) and merges only when they require the CI checks and an up-to-date branch, with no bypass for the merging account. If they do not, it merges nothing and says so in the report. This is the only guard that closes the gap between the last read of `main` and the merge call, so it is a prerequisite, not a backstop.
6. **CI.** Every job is green on the current head, and that head contains the current `main`. After the pending CI change (#68) merges, the jobs are `ci-ok` and both `docs` jobs.
7. **Merge.** Squash, with the expected head SHA. At most one merge per run, as the routine's first step, before any new work.
8. **After the merge.** Wait for `main`'s own CI run. If it fails, open a revert pull request as a held draft, stop merging until the user says to go on, and send the user one phone push.
9. **Reporting.** The run's report names each merge, the two run ids it relied on and the rules it read on `main`, and its one phone push names the pull request.

**The ruleset is set by the user.** Only the user can add a branch ruleset on `main` in the repository settings; Claude sessions cannot change settings. Until it exists, option A or B merges nothing (gate 5). GIT_GUIDELINES.md already recommends protected `main` with required checks.

**The user's veto.** Before the run that would merge, add the `hold` label or switch the pull request to draft. A pull request comment does not count, because every writer posts as the same account.

**Trial.** Fourteen days. Then the routine's report lists what merged, the days from opening to merge and any revert, and the user decides whether to keep the option.

## 5. Proposed text for each option

### Option A

- Skill hard limit, replacing "**Never merge.** Do not merge or squash any pull request, push to `main`, approve, enable auto-merge, or close or reopen pull requests.":

  > **Merge only by step 1e.** Merge nothing except as step 1e allows: at most one pull request this skill opened per run, squashed, after every gate of step 1e holds. Never push to `main`, approve, enable GitHub auto-merge, or close or reopen pull requests.

- New skill step 1e, "Merge one ready pull request": the nine gates of section 4, word for word, plus "skip step 1e while `state.json` has `merge_paused: true`".
- Prompt constraint 4, replacing its first sentence: "Merge only as the skill's step 1e allows (at most one of this routine's own pull requests per run, after two substantive clean ChatGPT rounds on the current head and the current main, green CI, and a ruleset on main that requires the checks and an up-to-date branch)."
- README.md, Development guidelines: "nothing merges into `main` without the user's word, except that the bug fix may merge one of its own pull requests per run once the ruleset on `main` is in force, CI is green and ChatGPT has confirmed that head against that `main` twice (see the merge gate in `docs/CLAUDE_WORKFLOW.md`)."
- docs/CLAUDE_WORKFLOW.md, bug fix: "**Merges only its own, and only when every gate holds.**" followed by a one-line summary of the gates. Merge gate: a new bullet with the same exception, and "the scheduled bug fix never merges" removed.

### Option B

As option A, with gate 1 limited to mirrors, coverage and typing pull requests, and the README and CLAUDE_WORKFLOW sentences naming those three kinds.

### Option C

- No change to the hard limit or to the prompt's constraint 4.
- New report step: after maintaining its pull requests, the routine lists those that pass gates 1 to 6 and posts one decision card in its thread: "Merge these N pull requests in this order?". The user's tap is the user's word for exactly those pull requests and heads; the thread session that receives it merges them one by one, bringing `main` into each branch and waiting for CI before each merge.
- docs/CLAUDE_WORKFLOW.md, merge gate: one bullet describing the card.

### Option D

No change.

## 6. How to undo

- **Stop auto-merging:** the user says "stop auto-merge" in the bug fix's thread. The skill goes back to version 15.3 and the prompt to version 13 from the next run; a docs pull request restores README and CLAUDE_WORKFLOW.
- **Stop one pull request:** add the `hold` label, or switch it to draft.
- **Undo a merge:** a revert pull request of the squash commit, merged by the user.
- **The ruleset** can stay, since GIT_GUIDELINES.md already recommends it, or be removed in the repository settings.

## 7. Review history and open questions

ChatGPT review of 2026-11-21 ([comment 7068663206](https://github.com/sasasqt/invest/pull/70#issuecomment-7068663206), head 86e4ac2, "Changes needed"): four findings on the proposed gates and the evidence table, none on live code.

- INV-PR70-001 (medium): gate 4 did not say what a confirmation is, so a clean notice, a copied marker or one review plus its notice could have counted as two. Now gate 4 counts substantive round markers only, with distinct run ids, bound to head and target, notices count zero, and the provenance limit is stated.
- INV-PR70-002 (medium): the merge call pins the head, not `main`, so a last read of `main` cannot close the race. Now the ruleset on `main` is gate 5, checked before each merge; without it nothing merges.
- INV-PR70-004 (medium): confirmations were bound to the head only, with an exemption for one conflict-free merge of `main`. Now they are bound to head and target and the exemption is gone; section 3 shows the slower throughput this costs.
- INV-PR70-003 (low): the #51 example in section 2 had the defect and the fix the wrong way round. Corrected.

Open questions for the next review:

1. Is there any check, available to a session with repository scope, that proves a comment came from the ChatGPT routine? If not, is a separate GitHub account for that routine worth setting up before option A or B starts?
2. Under option A with confirmations bound to head and target, is about one merge every two days acceptable, or does that argue for option C (the one-tap card), which merges a whole batch on one tap?
3. Under option A, which other gate would have stopped #33, #41 or #51 if ChatGPT had missed its defect?
4. Is anything in gates 1, 2 and 5 hard to check automatically, or easy to read two ways? Gate 5 needs the exact rule names GitHub returns for required status checks and the up-to-date requirement.
