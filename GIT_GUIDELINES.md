# Git Development Guidelines

These guidelines apply to both components in this repository. Keep `data-pipeline/` and `data-mining-framework/` together on `main`, with independent implementations and a shared dataset contract.

## Branching

- Keep `main` suitable for other contributors to build on. Use short-lived branches for new work and merge through pull requests.
- Name branches by purpose, such as `feat/pipeline-csv-export`, `feat/mining-csv-reader`, `fix/pipeline-null-handling`, or `docs/dataset-contract`.
- Create branches from the current `main`. Avoid permanent component branches: folders provide component separation, while branches represent changes.
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
- Configure protected `main` in repository settings when CI and collaboration are introduced: required checks, review requirements appropriate to the team, and restrictions on force pushes and deletion. These settings are recommendations and are not configured by this document.
- Choose a consistent merge strategy. Squash merging is a suitable default for focused feature branches; preserve individual commits when their history is useful.

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
