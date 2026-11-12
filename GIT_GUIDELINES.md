# Git Development Guidelines

These guidelines apply to all three components in this repository. Organize `data-pipeline/`, `data-mining-framework/`, and `strategy-evaluation/` by folders, with independent implementations and versioned artifact contracts. Branches organize development and releases; there is no requirement to keep all work on `main` or retain only that branch.

## Branching

- Keep `main` suitable for other contributors to build on. Use short-lived branches for new work and merge through pull requests.
- Name branches by purpose, such as `feat/pipeline-csv-export`, `feat/mining-csv-reader`, `fix/pipeline-null-handling`, or `docs/dataset-contract`.
- Create branches from the current `main`. Avoid permanent component branches: folders provide component separation, while branches represent changes.
- Use experiment or release branches when isolation or supported-release maintenance warrants them. Give them a clear purpose and integration or retirement plan; short-lived feature branches remain the default for ordinary changes.
- Keep one coherent task per branch. Coordinate changes to the shared dataset contract with both producer and consumer behavior.
- In isolated cloud tasks, use the existing checkout. Create additional Git worktrees only when explicitly requested.

Example for a clean checkout:

```sh
git status --short
git fetch origin
git switch main
git merge --ff-only origin/main
git switch -c feat/pipeline-csv-export
```

If `origin/main` is unavailable because the checkout uses a restricted fetch configuration, fetch it explicitly with `git fetch origin refs/heads/main:refs/remotes/origin/main`. Investigate divergence rather than resetting local work to make the update succeed.

## Commits

- Make focused commits that describe a meaningful change. Avoid mixing formatting, unrelated fixes, and feature implementation.
- Use a concise, imperative subject, such as `Add CSV dataset validation`. Add a body when the reason, tradeoff, or compatibility impact needs explanation.
- Stage explicit files or use `git add -p` for selected changes. Review the staged diff before committing; unstaged changes are not included in the commit.
- Include relevant tests and documentation with behavior changes. Avoid commits containing failing intermediate states on shared branches.
- Commit dependency declarations and their lockfiles together when dependencies change.
- Never commit secrets, virtual environments, caches, generated datasets, or large artifacts by accident. Use artifact storage or Git LFS when large versioned assets are actually required.

Typical review before a commit:

```sh
git status --short
git diff
git add path/to/changed-file path/to/relevant-test
git diff --cached --check
git diff --cached
git commit -m "Describe the change"
```

## Synchronization and history

- Fetch before integrating remote work. Prefer explicit fetch and merge/rebase decisions over an unexplained `git pull`.
- Rebase unpublished local commits when it simplifies review. Use merging for shared branches unless collaborators explicitly agree to a history rewrite.
- Do not amend, rebase, or force-push `main` or another contributor's published history without explicit coordination.
- If rewriting your own published feature branch is agreed upon, fetch first, inspect the remote changes, and use `--force-with-lease` rather than plain `--force`. A lease does not replace checking for work you might overwrite.
- Push the intended branch explicitly and verify the remote result. Delete merged feature branches after confirming their work is preserved.

## Pull requests and checks

- Describe the concrete problem, resulting behavior, relevant validation, and any limitations. Link related issues when available.
- Keep pull requests small enough to review as a coherent change. Explain cross-component edits and dataset contract compatibility.
- Run checks appropriate to the change. For Python behavior changes, use the component's formatting, linting, type checking, tests, and packaging checks once those tools exist. Documentation-only changes need link and whitespace validation rather than invented application tests.
- Distinguish passing, failing, skipped, and unrun checks. Do not claim readiness from a zero-test run.
- Consider Linux and Windows in every change, following the [Linux and Windows rules](PYTHON_GUIDELINES.md#linux-and-windows). Until CI runs on Windows, say in the pull request how Windows behavior was checked, or that it was not.
- Configure protected `main` in repository settings when CI and collaboration are introduced: required checks, review requirements appropriate to the team, and restrictions on force pushes and deletion. These settings are recommendations and are not configured by this document.
- Choose a consistent merge strategy. Squash merging is a suitable default for focused feature branches; preserve individual commits when their history is useful.

### Before marking ready

The author applies the README's [three development rules](README.md#development-guidelines) before asking for review:

1. **Self-review with the review ladder.** Start at round 1 and move up one round only when the current round earns it (the one exception is the extra full-diff round below): a full-diff round whose verified findings lead to non-trivial fixes (they change logic, a public interface or saved outputs, or span several functions), or a fix-commits round that finds a real defect in the fix code. Docs-, comment-, rename-, test- or formatting-only fixes never move the pull request up. A real defect is a verified finding with a regression test that fails before the fix.

   | Round | Model | Effort | Scope |
   |---|---|---|---|
   | 1 | Opus | high | Full diff |
   | 2 | Opus | medium | Fix commits |
   | 3 | Fable | high | Full diff |
   | 4 | Fable | medium | Fix commits |
   | 5 | Fable | xhigh | Full diff |
   | 6 | Fable | high | Fix commits |
   | 7 | Fable | max | Full diff |
   | 8 | Fable | xhigh | Fix commits |

   - Each round is a `/code-review <effort>` run (or an equivalent adversarial review) with the named model. **Full diff** is the whole pull request. **Fix commits** is only the commits that fixed the previous round's findings, plus the whole functions they touch, reviewed with the previous round's findings and their outcomes.
   - Run each full-diff round fresh: show it the earlier findings only after it has reported its own, so it does not re-check the same spots.
   - Fable rounds may run as a subagent so the main session keeps its model.
   - If round 8 still finds a real defect, stop and say "checkpoint due" ([RAPID_DEVELOPMENT.md §11](RAPID_DEVELOPMENT.md#11-step-back-between-milestones)). The person who requested the change chooses: redesign, a multi-agent review, or accept with the defect recorded in TODO.
   - The same ladder applies to non-trivial pushes that answer a reviewer's comments.
   - A bug found after the pull request was marked ready (by a reviewer or the nightly bug hunt) means the next review of that area starts at round 3.
   - If the ladder would end after a single full-diff round, also run the next full-diff round (round 3 after round 1, round 5 after round 3), fresh, when either holds: the step 4 workflow, run on `main` and on the branch, shows any difference in metrics, verdicts or decisions, even one the change explains; or the pull request changes more than about 100 lines of source code outside tests (Markdown, run records and other generated output do not count). Check both again on the final code. If the current round's fixes earned the fix-commits round, run that first. Say in the pull request which condition triggered the extra round; climbing after it follows the usual rule.
2. **Verify every finding.** Treat each one as a claim: reproduce it, then fix it or record why it does not hold. Keep blocking findings separate from optional cleanups.
   - A finding kept as is needs a checked reason, just as a fix needs a test. If it is the same kind of problem as a finding being fixed, ask the person who requested the change instead of deciding alone.
   - When a later pass contradicts an earlier decision, decide once and record why; do not switch the code back and forth between passes.
3. **Fix the class, not just the instance.** Search for the same pattern elsewhere and add a regression test that fails before the fix and passes after it. Never relax an existing assertion just so new code passes.
4. **Pair it with end-to-end checks.** A diff review cannot see cross-workflow problems such as two components using different conventions. Run the affected workflow on its real inputs and compare outputs across reports, not only unchanged metrics. Rerun the checks and the workflow on the final code, after the last review fix.
5. **State the result in the pull request:** the round, model, level, scope and finding count of each review pass, how each finding was resolved (fixed, or kept and why), and the checks run.
   - **Once the fixes for a reviewer's findings exist, put them where the reviewer looks.** Either push them to the existing pull request, edit its description (each finding, how it was resolved, the extra review round and checks) and answer the findings in a comment, or close the pull request and open a new one that carries the fixes, the old review record and a link back. Edit the existing pull request by default; close and recreate only when the branch history or scope changed so much that the old description and review no longer describe it. Fixes that live only on a branch or in a thread do not count as delivered.
6. **Record unrelated bugs; don't fix them here.** A bug found while fixing another, which is not the same class or root cause (step 3 still applies to those) and is not needed to make this fix or its tests correct, stays out of this pull request. Reproduce it if you can, then record it:
   - as a new unchecked `REVIEW-xx` item in [TODO.md](TODO.md) with its location, severity and how to reproduce it;
   - in the pull request description under "Found, not fixed", with the TODO id.

   If it is high severity, or it blocks this fix or its tests, stop and ask the person who requested the change before going on.
7. **Carry new bug-hunt findings into TODO.** The nightly bug hunt is report-only, so its findings list lives outside the repository. Each new **medium** or **high** finding it reports gets an unchecked `REVIEW-xx` item in [TODO.md](TODO.md) in the next pull request that fixes bugs, or in the next pull request of any kind when none is planned. Give the item the hunt's finding id (for example `BH-2026-10-08-1`), its location, severity and how to reproduce it, and group it with an existing open item of the same area when one exists. Low findings stay in the hunt's list until a fix pull request picks them up.

Green CI proves only what the tests already ask; it is not readiness on its own.

### Hardening rounds

When the person who requested a change asks to make it bug free or to harden it, review and fix it in rounds. Hardening rounds take the place of the review ladder for that change: the ladder's table, its climbing rule and its round 8 "checkpoint due" stop do not apply, while steps 2 to 7 of [Before marking ready](#before-marking-ready) still do. The rounds go on until one of the stops in steps 3 and 4.

1. **Run each round with independent reviewers.** A round has up to three reviewers, run in parallel, each with its own lens, scratch folder and port range, and every safety limit of the task in its prompt (including indirect routes such as configuration files and environment variables). Reviewers run on the model and effort the requester sets for the task; otherwise on Fable at xhigh effort, or on Opus at xhigh effort when Fable cannot run, with max effort only where steps 3 and 4 ask for it. A real bug is reproducible wrong behavior: it breaks a documented contract (such as [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) or a `CONTRACT.md` written for the code) or the documentation, crashes, hangs, loses data or misleads. Known, deliberate and purely cosmetic items are fixed when cheap but do not keep the rounds going. Findings outside the code the requester asked to harden follow step 6 of Before marking ready (recorded in TODO, not fixed here) and do not keep the rounds going either. A finding counts only with a check that fails on the current version and passes on the fix, and the check stays in a suite. Apply all confirmed fixes to the pull request's branch, rerun every suite, and add one line per round to the pull request description: findings by severity, checks added and pass counts.
2. **Rate severity by outcome, not by likelihood.** In these rounds a finding is **low** only when it fails closed in a normal run with any test-only check mode switched off, where one exists (a refusal or an error exit that changes nothing outside the run's own folders), or when it lives only in that test mode, a test, a document or wording. Every other finding is at least **medium**, however unlikely its trigger: for example one that deletes or changes files it should not, exposes data or secrets, hangs, or reports a wrong number, verdict or pass as valid. The author re-rates every reviewer's finding by this rule before counting severities or calling a round all-low.
3. **Stop at a clean round.** Stop when a round finds no real bug. If that round ran below max effort, one confirming round at max effort must also come back clean. Unless the requester sets another cap, stop after 10 rounds: fix what was found and run the suites, but keep the pull request a draft; report and wait for the requester.
4. **Or stop early after all-low rounds.** The rounds may also stop at a Fable round at max effort whose findings are all low, when it directly follows either one all-low Fable round or three consecutive all-low rounds of which at least one ran on Opus. When the rounds run on Opus only (Fable is at its usage limit, or the requester chose Opus for a while), pause after three consecutive all-low rounds instead of starting a fourth Opus round: save the progress so far (findings, fixes, checks and round count) so the work can resume, tell the requester, and run that one Fable round at max effort as soon as Fable may run again. If its findings are all low, the rounds stop; otherwise they go on as usual. Every finding is still fixed with its check and every suite rerun. If the stopping round's fixes change runtime code (not only tests or documents), one reviewer on that round's model at max effort checks only those fix commits: if it finds nothing above low, its low findings are fixed with checks and the rounds stop; otherwise there is no early stop and the rounds go on. An early stop counts as a clean round.
5. **Keep the pull request a draft until a stop.** The pull request stays a draft (not marked ready, not merged), and no package release or published research result is made from it, until a clean round or an early stop. Then run every suite, with the contract checks on where they exist, and the reference comparisons (at least the end-to-end run of step 4 of Before marking ready, on `main` and on the branch), and report the pass count per suite, plus coverage and mutation scores where measured, before marking it ready.

Why the early stop looks like this: on draft pull request #36, seven consecutive all-low Opus rounds were followed by a medium finding that had been in the code from the start, and two findings, one that deleted files outside the run and one that copied another branch's files into the code under audit, had been rated low only because their trigger was unusual. Rounds on a single model can keep missing the same thing, and a likelihood-based "low" hides real harm.

### When reviewing

1. **Judge design first, style last:** design, then functionality, complexity and tests; naming, comments and style after ([Google review guide](https://google.github.io/eng-practices/review/reviewer/looking-for.html)).
2. **Read the change in context,** checking how it fits the whole system and the workflows that consume it, not just the diff.
3. **Review the tests as hard as the code:** would they fail if the code were wrong?
4. **Check that documentation matches behavior,** and that every claim in it ("same", "consistent", "complete") is backed by a check at that scope.
5. **Approve on improvement, not perfection,** once the change clearly improves code health ([Google review standard](https://google.github.io/eng-practices/review/reviewer/standard.html)); label nits as optional.
6. **Keep reviews small.** Defect detection falls with review size; a few hundred lines per sitting is a practical limit, so ask for large changes to be split.

## Conflict resolution

- Start an integration with a clean working tree, or preserve local changes deliberately first. Inspect `git status` to identify the operation and affected files.
- Resolve conflicts by understanding both changes, especially schema, dependency, and test changes. Do not select an entire side just to remove conflict markers.
- Rerun affected checks, inspect the final diff, stage resolved files, and continue the merge or rebase.
- Use `git merge --abort` or `git rebase --abort` to abandon the corresponding operation when appropriate. Avoid destructive cleanup as a substitute for diagnosis.

## Recovery and local work

- Inspect `git status`, `git diff`, and the target paths before any cleanup, restore, or reset operation.
- Preserve changes you do not own. Do not use `git reset --hard`, `git clean -fd`, or file overwrites to discard unexplained changes.
- Use `git revert <commit>` to undo a published change while preserving shared history. Review and test the resulting change before pushing.
- Use `git reflog` to locate previous commit tips after an accidental local history change. Reflog cannot recover every untracked or unstaged file.
- If stashing is necessary, name the stash and inspect it before applying. Default stashing omits untracked files; `git stash push -u` includes them but still omits ignored files. Do not treat a stash as a remote backup.

## Security and repository hygiene

- Review new files and staged content for credentials or sensitive data. `.gitignore` only prevents adding matching untracked files; it does not remove files already tracked or erase history.
- If a credential is committed, revoke or rotate it immediately and coordinate incident handling. Deleting the file in a later commit does not remove exposure; history cleanup is a separate, coordinated operation.
- Use existing platform authentication and credential helpers. Never embed tokens in remote URLs or scripts.
- Avoid printing credential-bearing configuration or remote URLs when troubleshooting. Inspect sanitized identities and credential presence only.
- Use `.gitattributes` when the project needs explicit line-ending or binary-file rules. Avoid repository-wide normalization mixed into functional changes.
- Keep local environment settings out of Git; commit sanitized examples when useful. Follow [Python guidelines](PYTHON_GUIDELINES.md) for dependency and generated-output handling.

## Definition of done

A Git change is complete when the intended diff is reviewed, relevant validation is recorded, commits are understandable, the intended remote branch is verified after a requested push, and unrelated user work remains intact.
