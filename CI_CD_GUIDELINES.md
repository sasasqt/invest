# CI/CD Guidelines

How changes are checked, released, and turned into reproducible research results. The workflow lives in [`.github/workflows/ci.yml`](.github/workflows/ci.yml); keep this document and that file consistent.

## What CI checks today

Every pull request and every push to `main` runs:

| Job | Checks |
|---|---|
| `checks` (Python 3.11 and 3.13) | `uv sync --frozen`, `ruff format --check`, `ruff check`, `mypy` on all three `src/` trees, and `pytest` with branch coverage |
| `independent-install` (one per component) | Installs the component into a clean venv with only its declared dependencies and runs its own tests. Also fails if evaluation can import mining. |

A PR is mergeable only when all jobs are green on its latest commit.

## Principles

- **Same commands locally and in CI.** CI runs exactly the commands listed in the [Python guidelines](PYTHON_GUIDELINES.md#development-checks). If you add a check, add it in both places in the same change.
- **Fast and deterministic.** Tests use small synthetic fixtures, fixed seeds and no network. A run over about 5 minutes or a test that depends on the clock or a live service needs fixing, not a retry.
- **Frozen dependencies.** Install with `uv sync --frozen` from the committed `uv.lock`. Dependency changes update `pyproject.toml` and `uv.lock` in the same commit, and their CI run is the review evidence.
- **Least privilege.** Workflows default to `permissions: contents: read`. A job that needs more (publishing a release, writing comments) declares it in that job only.
- **Pinned actions.** Reference third-party actions by full commit SHA with the version in a comment (`uses: actions/checkout@<sha> # v4.4.0`). Update pins deliberately, ideally through Dependabot or Renovate PRs, and read the changelog.
- **No secrets in pull-request jobs.** Jobs triggered by `pull_request` must not need credentials. Never use `pull_request_target` to run code from a PR branch. Store data-vendor keys as environment secrets available only to protected-branch or manual workflows.
- **Never weaken a check to get green.** Don't skip, mark `xfail`, or delete a failing test, loosen a tolerance, or add a `# type: ignore` without a root cause recorded in the commit message. A failing test is a bug until proven otherwise; re-run once only for infrastructure failures (checkout, install, runner loss).
- **Fail on warnings that signal bugs.** `RuntimeWarning` from project code is an error in pytest (see `filterwarnings` in `pyproject.toml`). It usually means a division by zero or NaN propagation.
- **Required checks on `main`.** Protect `main`: require the CI jobs above, at least one review, and an up-to-date branch before merge. Prefer squash or merge commits per the [Git guidelines](GIT_GUIDELINES.md); never force-push `main`.

## What every change must keep green

- **Contract compatibility.** Changes to `invest_data.bundle` or `invest_data.schemas` must keep reading existing bundles. Incompatible changes bump `contract_version` and add a reader for the old version plus fixtures for both.
- **Causality tests.** The tests showing that future data cannot change past signals, fills, or equity are a release gate. A change that needs to edit them needs a reviewer who understands why.
- **Accounting reconciliation.** The engine raises `AccountingError` when equity does not reconcile; tests must exercise every cost type that is added.
- **Component independence.** Evaluation must not import mining, and neither may import another component's private modules. The `independent-install` job enforces this.

## Continuous delivery: releases

This is a library and research toolkit, so "delivery" means versioned packages and reproducible results, not a deployed service.

1. **Versioning.** Each component follows semantic versioning in its own `pyproject.toml`. Bump the minor version for new behavior, the major version for breaking changes to a public API, CLI, or artifact contract, and record the change in a `CHANGELOG.md` entry.
2. **Tagging.** Release from `main` only, with tags `<package>-v<version>` (for example `invest-evaluation-v0.2.0`).
3. **Build and verify.** A release workflow (to be added; see [TODO.md](TODO.md) QUALITY-01) runs `uv build --package <name>`, installs the wheel into a clean environment, runs the component's tests and a CLI smoke test against it, then publishes. Use PyPI trusted publishing (OIDC) rather than stored API tokens.
4. **Operator or contract changes.** If `OPERATOR_VERSION`, `ARTIFACT_VERSION`, or `CONTRACT_VERSION` changes, the release notes must say which saved factors, signals, or bundles need regenerating.

## Reproducible research runs

Treat a published research result like a release:

- Run it from a clean, committed revision. The evaluation manifest records `code_revision`; a run from a dirty tree is exploratory only.
- Use the frozen lockfile, fixed seeds, and dataset bundles identified by `content_sha256`.
- Keep generated outputs under `artifacts/` (ignored by Git). Archive results that matter in an artifact store with their manifest, not in the repository.
- Scheduled jobs (for example nightly data refreshes or prospective paper-trading evaluations) run as separate workflows with their own secrets and must never push to `main`. They publish new immutable bundles or reports and fail loudly on validation errors.

## Adding or changing CI

- Change the workflow in a focused PR that explains what the new check catches.
- Prove a new check works by showing it fail on a deliberately broken commit or a test case, then pass.
- Keep job names stable once they are required in branch protection; renaming a required job silently removes protection.
- Update this document, the README, and the Python guidelines in the same change.
