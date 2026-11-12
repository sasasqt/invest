# Python Development Guidelines

Use these guidelines when building this repository. The generic example layout below uses a single package named `invest`; this repository applies it to its three components (`invest_data`, `invest_mining`, `invest_evaluation`) as described in the [architecture](docs/ARCHITECTURE.md). The commands in [Development checks](#development-checks) are the ones CI runs.

## Project structure

Use a `src` layout with one clearly named import package per component. The example below uses `invest`; this repository plans `invest_data`, `invest_mining`, and `invest_evaluation` in their respective component folders:

```text
pyproject.toml
README.md
src/
  invest/
    __init__.py
    domain/
    services/
    adapters/
    cli.py
tests/
  unit/
  integration/
  conftest.py
```

Create directories only when there is code that needs them. Small projects can start with a few modules instead of multiple layers.

- Put business rules and data models in `domain`; keep them independent of databases, HTTP clients, and command-line frameworks.
- Put application workflows in `services` and external integrations in `adapters`.
- Keep entry points thin: parse input, invoke a workflow, and format the result.
- Group modules by responsibility and keep public APIs small. Avoid miscellaneous `utils` modules and circular imports.

## Packaging and dependencies

- Declare package metadata, the supported Python range, build backend, dependencies, and tool settings in `pyproject.toml`. Prefer a maintained stable Python version supported by required libraries.
- Use a virtual environment. This repository uses `uv`: the root `pyproject.toml` declares a uv workspace whose members are the three components, with one committed `uv.lock` and frozen installs in CI. Each member keeps its own `pyproject.toml` and runtime dependencies so it still installs on its own; shared development tools are declared once at the root.
- A component may depend on another component only through an explicitly versioned public module (today: `invest_data.bundle` and `invest_data.schemas`), never on private modules. Evaluation must not depend on mining.
- Separate runtime dependencies from development tools. Add dependencies only when their maintenance cost is justified.
- Use standard packaging entry points for executable commands rather than modifying `sys.path`.
- Document installation, configuration, common commands, and troubleshooting in `README.md`.
- Preserve TLS, package signatures, and checksum verification. Never embed credentials in source or lockfiles.

## Design and extensibility

Apply [design by contract](DESIGN_BY_CONTRACT.md) to public APIs, artifact boundaries, state transitions, and numerical routines. Make obligations and guarantees explicit; enforce essential runtime validation with checks that remain active when Python assertions are disabled.

- Prefer simple functions and composition. Introduce classes when they manage meaningful state or enforce an invariant.
- Pass dependencies explicitly. Inject external clients, repositories, clocks, and random generators when tests or alternate implementations need control.
- Use `typing.Protocol` at boundaries with multiple implementations; do not introduce an interface for every class.
- Keep side effects at application boundaries. Avoid network requests, file writes, or service initialization during imports.
- Validate untrusted data at boundaries and turn it into typed internal representations (frozen dataclasses, `Literal` and enum types, `TypedDict`s; see [Use the type system](#use-the-type-system)).
- Use explicit configuration objects. Load environment variables at startup and fail clearly when required configuration is absent.
- Add extension points for demonstrated needs. Avoid speculative plugin systems, broad inheritance hierarchies, and premature abstractions.
- If handling financial amounts, use `decimal.Decimal` with explicit currency and rounding rules. Use timezone-aware timestamps and document units.

## Coding standards

- Follow PEP 8 naming conventions and PEP 257 docstring conventions. Let automated formatting handle layout.
- Use Ruff for linting and formatting, and mypy for type checking. Configure them in `pyproject.toml` and keep local and CI settings consistent.
- Annotate every function and keep mypy in strict mode, following [Use the type system](#use-the-type-system).
- Write docstrings that explain behavior, contracts, and exceptions; comments should explain decisions that code cannot make obvious.
- Catch specific exceptions. Preserve the original exception when adding context, and avoid silently swallowing failures.
- Use structured logging with appropriate levels. Never log secrets, access tokens, or sensitive customer data.
- Use context managers for resources and explicit timeouts for external requests. Retry only appropriate transient failures, with bounded backoff and attention to idempotency.

## Linux and Windows

Every change must work on both Linux and Windows. CI runs only on Linux until [BUILD-03](TODO.md#m1--packages-and-tooling) adds a Windows job (only the conditional audit workflow already runs the audit runner's host tests on Windows), so the author checks the Windows side when writing the code, not after a user reports it.

- **Paths:** build them with `pathlib.Path` and the `/` operator, never by joining strings with `/` or `\`. Compare paths as `Path` objects, not strings. Keep names valid on Windows: no `:` `*` `?` `"` `<` `>` `|`, no reserved names such as `CON` or `NUL`, no two names differing only in case, and full paths under 260 characters.
- **Text files:** pass `encoding="utf-8"` to every `open`, `read_text` and `write_text`. Without it, Python 3.11 to 3.14 on Windows uses the locale code page (often cp1252), which cannot encode characters such as `≥` or `→`. Pass `newline=""` to files read or written by the `csv` module, and `newline="\n"` when written text must be byte-identical across platforms (reports, manifests, hashed or committed files).
- **Renames and deletes:** use `os.replace` to overwrite a file. `os.rename` and `Path.rename` fail on Windows when the target exists, and no platform replaces a non-empty directory. Windows also refuses to rename or delete a file another handle has open, so close files (context managers) before moving or removing them, and do not reopen a `NamedTemporaryFile` by name while it is still open.
- **Processes:** call `subprocess` with an argument list, never `shell=True`. For Python subprocesses, use `sys.executable` (for example `[sys.executable, "-m", "package"]`) rather than a hard-coded `python3`. Run external programs directly (for example `["git", "status"]`), and avoid hard-coded paths such as `/bin/sh`. Windows starts worker processes with `spawn`, so multiprocessing code needs an `if __name__ == "__main__":` guard and picklable workers.
- **POSIX-only APIs:** avoid `fcntl`, `os.fork`, `resource`, `pwd`, POSIX signals such as `SIGKILL`, and permission bits from `os.chmod`. When one is needed, give it a Windows path and say so in the docstring.
- **Time zones:** Windows has no system time-zone database, so code that uses `zoneinfo` must declare the `tzdata` package as a dependency.
- **Scripts:** new tooling goes in Python. Existing `scripts/*.sh` need a bash (Git Bash or WSL on Windows); a change to them should not add tools Git Bash lacks.
- **Tests:** use `tmp_path` and `Path`, never `/tmp` or hard-coded separators. When a platform difference cannot run in CI, simulate it in a test (as REVIEW-07 did for Windows rename semantics) and say in the pull request that no Windows host was used.

## Use the type system

Let the type checker prove what it can before any test runs: a mistake that mypy can reject should not need a test, a reviewer or a user to find it. CI runs mypy in strict mode with the settings in `pyproject.toml`, on the three `src/` trees and `scripts/`. The rule covers all code, tests included; typing the code written before this rule is [QUALITY-04](TODO.md#m1--packages-and-tooling). Until QUALITY-04 adds the test trees to CI, annotate new test code fully and check its file with `uv run mypy <file>`; errors in functions written before the rule belong to QUALITY-04.

- **Strict and complete:** every function and method, private ones included, has full parameter and return annotations, and `[tool.mypy]` keeps `strict = true`. Do not loosen a mypy setting, widen a type to `Any`, or add an ignore or a `cast` just to make a change pass: like relaxing an assertion, that weakens a check. When one is unavoidable, the pull request says why.
- **Precise types, not `Any`:** annotate data that is not validated yet, such as parsed JSON or command-line input, as `object` (for parsed JSON, the `JSON` alias described under "Runtime checks stay at boundaries"), never `Any`, and turn it into a typed value at that boundary; `Any` appears only where a library returns it (`json.loads`; pandas objects, annotated as the pandas bullet says). Every `# type: ignore[<code>]` names its error code (mypy enforces this) and says why; every `cast` says what checked the value. Use only typing features that Python 3.11 has (for example not `typing.override`, which is 3.12), and not `typing_extensions`, which no component depends on at runtime.
- **Make invalid states unrepresentable:** a closed set of values (a status such as `insufficient_data`, a verdict, a confirmation use, a slice kind, a column type) is a `Literal` alias or an enum, not a bare `str`, and a chain of branches over it ends in `assert_never`, so a new value fails type checking until every branch handles it (where the chain already ends in a `raise` for bad input, keep its exception and raise it through a helper that takes the narrowed value as `Never`: `raise unhandled(kind, ValueError(f"unknown kind {kind!r}"))`, with `def unhandled(value: Never, error: E) -> E: return error` and `E = TypeVar("E", bound=Exception)` defined once per package; mypy reports an assignment such as `_exhaustive: Never = kind` there as unreachable once `warn_unreachable` is on, but not a `raise`). Identifiers or units that must not be mixed get their own `NewType`. Records are frozen dataclasses that check their invariants in `__post_init__`; JSON payloads with fixed keys are `TypedDict`s. Prefer a type that cannot hold a wrong value over a runtime check that rejects it later.
- **Check domain rules before reading data where the structure allows it:** when a rule can be decided from a structure before any data is read, for example the unit or scale of each node of a formula tree, check it over that structure (with mypy where the structure is written in code, with a checker over the tree's node types where it is built at run time) and refuse before reading data.
- **Runtime checks stay at boundaries:** types do not validate files, configuration, network answers or user input. Check those where they enter ([design by contract](DESIGN_BY_CONTRACT.md#3-enforce-contracts-at-the-right-layer)), and annotate the boundary parameter with what a caller can really pass (`object`, or for parsed JSON a `JSON` alias defined once per package, and once in `scripts/` if needed, in a private module of that package; never `Any`), not with what the check guarantees. For a dataclass field that `__post_init__` checks, keep the field's type and run the check on a local copy annotated `object`, so the field's readers keep the precise type. When mypy calls such a check unreachable, find out why: either the annotation claims more than the input guarantees (widen the annotation and keep the check), or mypy cannot follow the check, as with `isinstance(x, numbers.Integral)` on an `int` or `numbers.Real` together with `bool`; then rewrite the check in a form mypy follows, keeping its runtime behaviour. mypy skips everything after a statement it believes unreachable, so either case left in place leaves that code unchecked.
- **Fix the class with a type:** when a bug came from a mixed-up value, an unhandled case or an unexpected `None`, prefer a type change that makes mypy reject every sibling of the bug, and keep the regression test.
- **Test the types that carry a rule:** a type that encodes a rule (a `Literal` set, a `NewType`, a `TypedDict`) gets a type test: a file `tests/type_checks/check_<topic>.py` (never named `test_*.py`, which pytest would import and run) whose misuse sits inside a function that is never called, on a line marked `# type: ignore[<code>]`. Because `warn_unused_ignores` is on, mypy reports `Unused "type: ignore" comment [unused-ignore]` as soon as the misuse stops being an error. The packages ship a `py.typed` marker, so mypy reads their types also when it checks these files on their own. The pull request that adds the first such file appends `tests/type_checks` to the mypy line in `.github/workflows/ci.yml`, in [Development checks](#development-checks) and in README.md.
- **pandas and pyarrow:** neither ships a `py.typed` marker (so mypy ignores pandas' inline annotations) and `pandas-stubs` is not installed, so mypy sees every `DataFrame`, `Series` and pyarrow object as `Any`. Annotate them anyway, and check column names and dtypes at the boundary where a frame enters.

## Testing strategy

Use pytest. Test observable behavior and business requirements rather than private implementation details.

- **Unit tests:** exercise business rules without external services. Cover normal behavior, boundaries, invalid input, and failure paths.
- **Integration tests:** exercise real boundaries, such as serialization, database queries, and API adapters, using isolated temporary resources or dedicated test services.
- **Smoke tests:** exercise an actual entry point or representative end-to-end workflow after installation.
- Use descriptive test names and arrange–act–assert organization. Parameterize related cases where it improves clarity.
- Keep fixtures small and scoped. Use `tmp_path` for temporary files, clean up resources, and avoid shared mutable state.
- Mock external boundaries only when needed; avoid mocking the behavior under test. Use realistic integration tests to verify assumptions hidden by mocks.
- Make tests deterministic: control time and randomness, and keep ordinary tests independent of live network access and credentials.
- Register markers such as `integration` in pytest configuration. Ensure CI runs each required category explicitly; skipping integration tests must not be reported as full validation.
- For each bug fix, add a regression test that fails before the fix and passes afterward.
- Use branch coverage to find missing behavior, especially in critical business logic. A percentage target does not replace meaningful assertions.

## Development checks

Audit-runner changes also require the [conditional Linux/Docker checks](CI_CD_GUIDELINES.md#conditional-isolated-audit-checks).
From `audits/gpt/runner`, run `python -m unittest -v test_guards test_output_collection test_execution_logs test_host_safety` on Linux or Windows (it needs `packaging`; the suites switch on the `CONTRACT_CHECKS=1` contract checks themselves).
On a disposable Linux/Docker host, run `python collection_checks.py --python-version 3.11 --output /path/to/new-collection-check`
and repeat with `--python-version 3.13` and a separate new output directory. This
uses generated fixtures and records the Docker image identity; it is not a
product benchmark or a substitute for the normal checks below.

Run these from the repository root (CI runs the same commands on Python 3.11 and 3.13, plus an install of each component on its own):

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src scripts
uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch --cov-report=term-missing
uv run python scripts/check_markdown_links.py
```

CI also builds all three wheels (`uv build --all-packages`), installs them in a clean environment, smoke-tests the CLIs, and runs the component and end-to-end tests against the installed packages. A zero-test run does not demonstrate readiness.

## Continuous integration and change review

- Run formatting, linting, type checks, required tests, and packaging checks on pull requests.
- Test the minimum supported Python version and the primary development version; expand the matrix when compatibility requirements justify it.
- Install from the committed lockfile and use minimal CI permissions. Pin third-party actions to reviewed commit SHAs and maintain those pins.
- Keep changes focused. Explain the behavior changed, why it changed, and how it was validated.
- Before marking a pull request ready, follow the [author steps](GIT_GUIDELINES.md#before-marking-ready) (self-review, verified findings, end-to-end checks); review others' changes [this way](GIT_GUIDELINES.md#when-reviewing).
- Document public API changes and configuration requirements. Use deprecation paths when downstream users depend on existing behavior.
- Review dependencies regularly and investigate security findings in context.

## Cloud development workflow

Follow the [rapid development guidelines](RAPID_DEVELOPMENT.md) for small working increments, fast feedback, and validation appropriate to the change.

Use the existing checkout in the isolated cloud task. Do not create an additional Git worktree unless explicitly requested. Keep installation steps repeatable and separate retained dependencies from services that must restart. Document service startup and functional readiness checks when services are introduced.

## Definition of done

A change is complete when its behavior is implemented, relevant tests execute and pass, required quality and packaging checks pass, documentation reflects public changes, and any skipped checks or known limitations are stated explicitly.
