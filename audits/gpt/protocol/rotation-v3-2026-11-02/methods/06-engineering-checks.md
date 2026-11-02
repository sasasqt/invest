#### 6. Establish the test environment and run the existing checks

Discover commands from the audited revision, rather than blindly relying on these examples.

- Install from the committed lockfile in an isolated environment. Do not update dependency specifications or the lockfile to make checks pass.

- Keep repository-executed code separate from connector credentials and other secrets. Use an environment that actually prevents access to credentials, not merely one that removes a few environment variables.

- Obtain dependencies during a controlled setup phase if permitted; run tests and benchmarks without live-network dependencies where practical.

- If installation or network access fails, record the exact failure, use available checks, and recheck once where a transient failure is plausible. Never report unavailable checks as passed.

- Run formatting in check mode, lint, type checks, the complete declared test suite with branch coverage, and documentation/link checks.

- Build every package; test installed wheels in a clean environment outside the source import path; run CLI smoke checks and each component's independent-install tests.

- Exercise each supported CI Python version where available. Inspect CI evidence at the same SHA for unavailable versions, distinguishing it from local execution. Do not claim Windows execution from Linux tests.

- Verify which package files were actually imported, especially during wheel and independence checks.

- Reproduce every job defined by the audited CI file, using a distinct environment and log for each interpreter, wheels and independent-install job. Run dependency setup alone first. Where resources and isolation permit, run at most three independent test jobs concurrently; benchmarks must wait until all jobs finish. Obtain a missing supported interpreter once through an available approved runtime/setup mechanism, otherwise record that job as not reproduced.

- Export per-file line and branch coverage as JSON and record the 25 slowest tests. Repeat the primary supported-interpreter suite with `PYTHONHASHSEED=12345` to investigate order/hash dependence; preserve both outcomes and diagnose differences before classifying a flaky test. Compare local and GitHub evidence only at the same SHA. A mismatch is a drift lead whose cause must be established, not automatically a product defect.

- Inspect uncollected test files, weak/no assertions, expected values derived from the implementation under test, skipped/xfail cases, warning filters, and decision code whose branches are uncovered. Prioritize source with line coverage below 60% while accounting for test importance and actual branch coverage. Do not install a new mutation-testing tool as part of this routine; use bounded audit-only perturbations where justified.

- Record collection counts, passes, failures, skips, expected failures, timeouts, warnings, durations and exit codes. If resuming a split test run, account for unique test IDs rather than adding overlapping counts.

- Do not weaken tests, suppress relevant warnings, change tolerances or patch product code to turn a failure green.

- Diagnose failures against the audited revision. Use an appropriate older revision only when needed to establish provenance; distinguish code defects, obsolete tests and environment limitations with evidence.

Example commands: discover and revalidate the audited revision's actual CI commands at execution:

```sh

uv sync --frozen

uv run ruff format --check .

uv run ruff check .

uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src

uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch --cov-report=term-missing

uv run python scripts/check_markdown_links.py

```

Redirect caches, coverage files, build outputs and other temporary artifacts outside the preserved checkout where supported. Use a disposable clone when a command requires writing within its checkout. Do not create additional Git worktrees.

