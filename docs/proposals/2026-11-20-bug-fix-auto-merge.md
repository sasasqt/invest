# Proposal: may the daily bug fix merge its own pull requests?

Draft for review, written 2026-11-20, revised 2026-11-21 after ChatGPT's first review and 2026-11-22 after the user's addition and a blind second review (section 7). **Nothing is decided.** The user picks one of the options below; until then the bug fix never merges and nothing on `main`, in the routine or in the repository settings changes. This file is in a draft pull request so that the ChatGPT open-PR review can check the options before the user picks one.

## 1. The rule today

- [README.md](../../README.md#development-guidelines) (Development guidelines): "nothing merges into `main` without the user's word."
- [docs/CLAUDE_WORKFLOW.md](../CLAUDE_WORKFLOW.md#bug-fix-daily), bug fix: "**Never merges.** It never merges, pushes to `main`, approves, enables auto-merge, or closes or reopens a pull request, and never force-pushes"; [merge gate](../CLAUDE_WORKFLOW.md#merge-gate): "the scheduled bug fix never merges."
- The bug-fix skill in the project library (version 15.3 by the project memory's change log; the file carries no version line), first hard limit: "**Never merge.** Do not merge or squash any pull request, push to `main`, approve, enable auto-merge, or close or reopen pull requests."
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

All must hold at merge time, checked by the routine from the pull request body, GitHub state and its own files. If one fails, nothing merges and the run's report says which gate failed and why.

1. **Which pull requests.** The head branch starts with `claude/project-thread-7rf56w-` (the routine's own). Ready for review, not a draft. No `hold` label. Under A: fix pull requests whose `Fixes:` line names only rows the hunt ledger rates low or medium (the routine's rating; ChatGPT's may differ, as on #51), docs-only pull requests, mirrors, coverage and typing. Under B: mirrors, coverage and typing only.
2. **Exclusions.** Any row in the `Fixes:` line rated high. "Checkpoint due" in the title. A `## Held for your decision` section whose question has no answer recorded in `decisions.md`. Any `[not second-reviewed]` mark in the body, or the pull request named in `state.json`'s `not_second_reviewed` (the usage guard skipped reviewer 2, so the signs below were never checked). Any hunk under `.github/`, in `uv.lock`, in a `pyproject.toml` dependency table (coverage floors under `[tool.invest.coverage]` are allowed), or in GIT_GUIDELINES.md, PYTHON_GUIDELINES.md, CI_CD_GUIDELINES.md, DESIGN_BY_CONTRACT.md, RAPID_DEVELOPMENT.md or README.md between `## Development guidelines` and the next `## ` heading, except the mypy and type-rule lines the skill lets a typing pull request change. And three signs that the fix is not settled (the user's rule of 2026-11-22):
   - a **design choice that changes behaviour or results**: a new refusal in place of a warning, a changed default, formula, or format or version constant, or a deliberate difference in the `## Checks` reference comparison between `main` and the branch, unless the body names what decides it: the spec line the fix implements (a doc or TODO item), a `decisions.md` entry, or the user's words in the routine's thread (quoted by the routine, so a record rather than proof). Step 8 adds this list to the body (section 5).
   - an **open question**: an item under "Decisions needed" in the most recent run report that names the pull request, its branch or any ID in its `Fixes:` line.
   - a **disagreement**: an item in `## Review` where reviewer 2's call differed from the run's and the run did not adopt reviewer 2's call (left as it was, or settled by the verifier). Calls about wording, names or the shape of a test that the run adopted stay with reviewer 2.
3. **Own reviews.** The `## Review` section lists the ladder rounds with every finding resolved, and every ChatGPT finding ID (`INV-PR<n>-…`) in the maintained comment has a later reply from the routine or a later commit.
4. **Two ChatGPT confirmations, bound to head and target.** In ChatGPT's one maintained comment: two `invest-pr-review-round:v1` markers with distinct `run` ids on two different dates, each with `head` equal to the current head and `target` equal to the current `main`, and each round's dated history entry recording "No blocking issues found" (a marker carries no conclusion, so a "Changes needed" round followed by a clean one on the same head is one confirmation, not two). A clean notice (`invest-clean-review`) counts zero, and so does any comment without a round marker. A new head or a new `main` starts the count again; there is no exemption for a conflict-free merge of `main`, because two reviews of the old `main` say nothing about the new integration. Dependencies and limits: (a) two rounds on one head need ChatGPT to review an unchanged head again, which it did on 2026-11-21 (#63, round 2) and not before; docs/GPT_OPENAI_ROUTINES.md and docs/CLAUDE_WORKFLOW.md still describe reuse (hunt row BF-2026-11-20-1), and if reuse returns the pull request waits and the report says so; (b) ChatGPT caps a head at five rounds or comments, so two confirmations fit; (c) the marker names are observed in ChatGPT's comments on #53, #63 and #70, not documented anywhere; (d) every writer uses the same GitHub account, so the markers and the dated history sit in one comment and cannot prove their author; the report quotes the run ids, and a separate GitHub account for the ChatGPT routine would make the author a hard check.
5. **Protection on `main`, checked before each merge.** Through GitHub's rulesets API: an active ruleset on `main` with a `required_status_checks` rule whose `strict_required_status_checks_policy` is true and whose contexts include every job gate 6 names, and whose `bypass_actors` is empty (field names to confirm against GitHub's API reference when the skill change is written). If it is missing, the routine merges nothing and says so. This is the only guard that closes the gap between the last read of `main` and the merge call: the call's expected SHA pins the head, not `main`.
6. **CI.** Every job is green on the current head, and that head contains the current `main`. Today: `checks (3.11)`, `checks (3.13)`, `wheels` and the three `independent-install` jobs; after #68 merges, `ci-ok` and both `docs` jobs.
7. **Merge.** Squash, with the expected head SHA. At most one merge per run, in step 1e, which runs before step 1, so that a maintenance push cannot change the head after the gates were read.
8. **After the merge.** Wait for `main`'s own CI run. If it fails, open a revert pull request as a held draft, set `merge_paused: true` in `state.json` until the user says to go on, and send the user one phone push.
9. **Reporting and the veto window.** The run's report names each merge, the two run ids and the rules it read on `main`, and lists the pull requests that would merge at the next run if the gates still hold; the routine's one phone push names them. The user stops one by adding the `hold` label or switching it to draft before the next run (both are read as GitHub state, not parsed from text, which is why a comment does not count).

**The ruleset is set by the user.** Only the user can add a branch ruleset on `main` in the repository settings; Claude sessions cannot change settings. Until it exists, option A or B merges nothing (gate 5). GIT_GUIDELINES.md already recommends protected `main` with required checks.

**Trial.** Fourteen days. Then the routine's report lists what merged, the days from opening to merge and any revert, and the user decides whether to keep the option.

## 5. Proposed text for each option

### Option A

- Skill hard limit, replacing "**Never merge.** Do not merge or squash any pull request, push to `main`, approve, enable auto-merge, or close or reopen pull requests.":

  > **Merge only by step 1e.** Merge nothing except as step 1e allows: at most one pull request this skill opened per run, squashed, after every gate of step 1e holds. Never push to `main`, approve, enable GitHub auto-merge, or close or reopen pull requests.

- New skill step 1e, "Merge one ready pull request": the nine gates of section 4, word for word, plus "skip step 1e while `state.json` has `merge_paused: true`".
- Skill step 8: the body gets a `## Design choices` list (each choice that changes behaviour or results, with the spec line, `decisions.md` entry or user's words that decides it) and keeps listing every judgment call with reviewer 2's call, so that gate 2's three signs can be read from the body alone. Step 9: the report names the pull requests that would merge at the next run (gate 9).
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

User's addition of 2026-11-22 (thread "Decide auto-merge for the daily bug fix"): gate 2 excludes three signs that a fix is not settled: a behaviour-changing judgment call with no decision of the user's behind it, an open "Decisions needed" item or `decisions.md` entry for the pull request, and a call that needed the verifier. The first sign is deliberately narrow: a typical fix carries many judgment calls (17 on the fix of 2026-11-02, by its run report; the report does not itemise them), and excluding every call without the user's decision would turn option A into option B in practice.

Blind second review of 2026-11-22 (one fresh Fable helper at xhigh, given the file and the sources, not the author's view): 10 findings, 3 high, 6 medium, 1 low, all adopted. The high ones: the fix's design choices are not among the skill's "judgment calls", so the first sign now reads from design choices and the `## Checks` comparison; the usage guard can skip reviewer 2, so a `[not second-reviewed]` mark now excludes; gate 4 depends on ChatGPT reviewing unchanged heads, which the docs still deny, so gate 4 names that dependency and its fallback. Among the medium ones: a round marker carries no conclusion (gate 4 now reads each round's dated entry); "the routine's latest report" is the previous run's and names bug IDs, not pull requests (sign 2 now matches the `Fixes:` IDs); the exclusions and gate 5 now name hunks and API fields; gate 7 runs before step 1. Adopted with a change: sign 3 counts a disagreement the run did not adopt, not every differing call, because a call the run adopted is settled. Not checked by the reviewer: GitHub's exact rule field names (no network), the list of 14 merged pull requests offline, the #63 marker text.

Open questions for the next review:

0. Are gate 2's three new signs checkable from the pull request body alone, once step 8 records for each call whether it changes behaviour or results? Is "changes behaviour or results" sharp enough, or does it need the list of kinds (refusal, formula, default, saved output, verdict) to be closed?
1. Is there any check, available to a session with repository scope, that proves a comment came from the ChatGPT routine? If not, is a separate GitHub account for that routine worth setting up before option A or B starts?
2. Under option A with confirmations bound to head and target, is about one merge every two days acceptable, or does that argue for option C (the one-tap card), which merges a whole batch on one tap?
3. Under option A, which other gate would have stopped #33, #41 or #51 if ChatGPT had missed its defect?
4. Is anything in gates 1, 2 and 5 hard to check automatically, or easy to read two ways? Gate 5 needs the exact rule names GitHub returns for required status checks and the up-to-date requirement.
