# Proposal: may the daily bug fix merge its own pull requests?

Draft for review, written 2026-11-20. **Nothing is decided.** The user picks one of the options below; until then the bug fix never merges and nothing on `main`, in the routine or in the repository settings changes. This file is in a draft pull request so that the ChatGPT open-PR review can check the options before the user picks one.

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
| Defects ChatGPT found after the routine's own review ladder | 3 of the 14: [#33](https://github.com/sasasqt/invest/pull/33) (a CSV with mixed time-zone offsets was published in part instead of refused), [#41](https://github.com/sasasqt/invest/pull/41) (bundle hashes checked on one read, scores computed from a second read), [#51](https://github.com/sasasqt/invest/pull/51) (the ledger was asked before the as-traded check). Plus a TODO.md merge conflict on [#53](https://github.com/sasasqt/invest/pull/53). All four were fixed before merging |
| Defects that reached `main` | none: no row of the bug-hunt ledger traces a code defect to a merged bug-fix pull request. One low row says these pull requests left README and ROADMAP's open-defect lists stale |
| What waiting cost | the runs of 2026-11-09, 11-10 and 11-11 opened nothing, because five of the routine's pull requests were open (its cap), all green and waiting only for a merge. The 2026-11-07 run could not open a finished fix because it overlapped the unmerged #34 |
| When ChatGPT reviews | every day at 21:00 Berlin ([GPT / OpenAI routines](../GPT_OPENAI_ROUTINES.md)). A clean review carries the marker `<!-- invest-clean-review:v1 pr=N head=SHA target=SHA -->` |
| When the bug fix runs | every day at 04:00 Berlin; a new pull request opens at about 05:00 |

What the evidence says: the routine's own ladder let about one pull request in five through with a real defect, and the ladder plus ChatGPT let none through. Any merge by the routine must therefore wait for ChatGPT. The user asks for **two** ChatGPT confirmations, and says ChatGPT's review behaviour changed on 2026-11-20 (until then, a pass over an unchanged head reused the earlier review without rerunning anything).

Risks specific to this repository:

1. **Stale CI.** Without protection, a squash merge goes through even when `main` moved after the last CI run.
2. **TODO.md and README conflicts.** Almost every bug-fix pull request adds REVIEW items. Each merge pushes a conflict onto the other open pull requests, and resolving it resets their CI and their ChatGPT review.
3. **One GitHub account.** ChatGPT, every Claude session and the user all write as `sasasqt`. A comment proves nothing about its author; only the marker's head and target SHAs can be checked. A merge by the routine also shows as the user's.
4. **Decisions inside fixes.** Some fixes carry the user's design calls. High-severity fixes change results the most.
5. **Undo.** A bad merge is undone by a revert pull request. That is easy for one squash commit and harder once later merges build on it.

## 3. Options

| | Option | What merges without the user | Effect |
|---|---|---|---|
| A | **Gated auto-merge, no high fixes** (recommended) | at most one bug-fix pull request per run that passes every gate in section 4 | no more cap stalls; about 2 days from opening to merge |
| B | Auto-merge mirrors, coverage and typing only | generated mirrors, tests-only and types-only pull requests, under the same gates | coverage and typing keep growing; the cap of five is unchanged, because those never count toward it |
| C | Daily one-tap merge card | nothing; after ChatGPT's pass, the routine posts one card listing the pull requests that pass the gates, and the user's one tap lets a thread merge them in order | about 1 to 2 days if the user taps daily; the rule stays as it is |
| D | Keep it manual | nothing | as today |

## 4. Gates (options A and B; option C uses them to build its list)

All must hold at merge time. If one fails, nothing merges and the run's report says which gate failed.

1. **Which pull requests.** Opened by this routine. Ready for review, not a draft. No `hold` label. Under A: fix pull requests whose fixed rows are all low or medium, docs-only pull requests, mirrors, coverage and typing. Under B: mirrors, coverage and typing only.
2. **Exclusions.** Any fixed row rated high. "Checkpoint due". A question still waiting in the body. Changes under `.github/`, to dependencies or `uv.lock`, or to the rule text of GIT_GUIDELINES.md, PYTHON_GUIDELINES.md, CI_CD_GUIDELINES.md, DESIGN_BY_CONTRACT.md, RAPID_DEVELOPMENT.md or README's Development guidelines.
3. **Own reviews.** The ladder rounds and reviewer 2's checks are in the body with every finding resolved, and no review comment is unanswered.
4. **Two ChatGPT confirmations.** Two clean reviews ("No blocking issues found", each with an `invest-clean-review` marker) from two separate daily passes, both with the marker's head equal to the current head. One exception keeps a pull request from waiting forever while `main` moves: the current head may be the reviewed head plus exactly one merge of `main` that applied without conflicts and changed nothing else.
5. **CI.** Every job is green on the current head, and that head contains the current `main`, re-read just before merging. After the pending CI change (#68) merges, the jobs are `ci-ok` and both `docs` jobs.
6. **Merge.** Squash, with the expected head SHA. At most one merge per run, as the routine's first step, before any new work.
7. **After the merge.** Wait for `main`'s own CI run. If it fails, open a revert pull request as a held draft, stop merging until the user says to go on, and send the user one phone push.
8. **Reporting.** The run's report names each merge and why it passed, and its one phone push names the pull request.

**Backstop, set by the user in GitHub.** A branch ruleset on `main` that requires the CI checks and "require branches to be up to date before merging". GitHub then refuses a stale or red merge even if the routine's own check has a bug. Claude sessions cannot change repository settings.

**The user's veto.** Before the run that would merge, add the `hold` label or switch the pull request to draft. A pull request comment does not count, because every writer posts as the same account.

**Trial.** Fourteen days. Then the routine's report lists what merged, the days from opening to merge and any revert, and the user decides whether to keep the option.

## 5. Proposed text for each option

### Option A

- Skill hard limit, replacing "**Never merge.** Do not merge or squash any pull request, push to `main`, approve, enable auto-merge, or close or reopen pull requests.":

  > **Merge only by step 1e.** Merge nothing except as step 1e allows: at most one pull request this skill opened per run, squashed, after every gate of step 1e holds. Never push to `main`, approve, enable GitHub auto-merge, or close or reopen pull requests.

- New skill step 1e, "Merge one ready pull request": the eight gates of section 4, word for word, plus "skip step 1e while `state.json` has `merge_paused: true`".
- Prompt constraint 4, replacing its first sentence: "Merge only as the skill's step 1e allows (at most one of this routine's own pull requests per run, after two clean ChatGPT reviews and green CI on a head that contains the current main)."
- README.md, Development guidelines: "nothing merges into `main` without the user's word, except that the bug fix may merge one of its own pull requests per run once CI is green and ChatGPT has confirmed it twice ([merge gate](docs/CLAUDE_WORKFLOW.md#merge-gate))."
- docs/CLAUDE_WORKFLOW.md, bug fix: "**Merges only its own, and only when every gate holds.**" followed by a one-line summary of the gates. Merge gate: a new bullet with the same exception, and "the scheduled bug fix never merges" removed.

### Option B

As option A, with gate 1 limited to mirrors, coverage and typing pull requests, and the README and CLAUDE_WORKFLOW sentences naming those three kinds.

### Option C

- No change to the hard limit or to the prompt's constraint 4.
- New report step: after maintaining its pull requests, the routine lists those that pass gates 1 to 5 and posts one decision card in its thread: "Merge these N pull requests in this order?". The user's tap is the user's word for exactly those pull requests and heads; the thread session that receives it merges them one by one, bringing `main` into each branch and waiting for CI before each merge.
- docs/CLAUDE_WORKFLOW.md, merge gate: one bullet describing the card.

### Option D

No change.

## 6. How to undo

- **Stop auto-merging:** the user says "stop auto-merge" in the bug fix's thread. The skill goes back to version 15.3 and the prompt to version 13 from the next run; a docs pull request restores README and CLAUDE_WORKFLOW.
- **Stop one pull request:** add the `hold` label, or switch it to draft.
- **Undo a merge:** a revert pull request of the squash commit, merged by the user.
- **The ruleset** can stay, since GIT_GUIDELINES.md already recommends it, or be removed in the repository settings.

## 7. Questions for reviewers

1. Is an `invest-clean-review` marker whose head equals the current head enough evidence of a clean review, given that every writer uses the same account?
2. Does gate 4's exception (one conflict-free merge of `main`, nothing else changed) open a hole? Is there a check, other than CI on the new head, that the merge changed nothing else?
3. Can `main` move between gate 5's last read and the squash merge? Without the ruleset, is re-reading `main` right before the merge call enough?
4. Under option A, which other gate would have stopped #33, #41 or #51 if ChatGPT had missed its defect?
5. Is anything in gates 1 and 2 hard to check automatically, or easy to read two ways?
