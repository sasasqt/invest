# Python Development Guidelines

Use these guidelines when building this repository. The repository is currently empty; the layout and commands below describe the recommended future setup, not an already installed application.

## Project structure

Use a `src` layout with one clearly named import package. For this project, `invest` is a reasonable default:

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
- Use a virtual environment. Select one dependency manager; `uv` is a suitable default. Commit its lockfile and use frozen installs in CI and repeatable environment setup.
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
- Validate untrusted data at boundaries and use typed internal representations, such as dataclasses, where useful.
- Use explicit configuration objects. Load environment variables at startup and fail clearly when required configuration is absent.
- Add extension points for demonstrated needs. Avoid speculative plugin systems, broad inheritance hierarchies, and premature abstractions.
- If handling financial amounts, use `decimal.Decimal` with explicit currency and rounding rules. Use timezone-aware timestamps and document units.

## Coding standards

- Follow PEP 8 naming conventions and PEP 257 docstring conventions. Let automated formatting handle layout.
- Use Ruff for linting and formatting, and mypy for type checking. Configure them in `pyproject.toml` and keep local and CI settings consistent.
- Add type hints to public APIs and important internal boundaries. Prefer precise types over `Any` and explain necessary suppressions.
- Write docstrings that explain behavior, contracts, and exceptions; comments should explain decisions that code cannot make obvious.
- Catch specific exceptions. Preserve the original exception when adding context, and avoid silently swallowing failures.
- Use structured logging with appropriate levels. Never log secrets, access tokens, or sensitive customer data.
- Use context managers for resources and explicit timeouts for external requests. Retry only appropriate transient failures, with bounded backoff and attention to idempotency.

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

After the package and development dependencies (`pytest`, `pytest-cov`, `ruff`, `mypy`, and `build`) are configured, the expected checks are:

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest --cov=invest --cov-branch --cov-report=term-missing
uv run python -m build
```

These commands are recommendations and have not been run against an implemented project. A zero-test run does not demonstrate readiness. For distributable packages, also install the built wheel in a clean environment and verify its imports and entry points.

## Continuous integration and change review

- Run formatting, linting, type checks, required tests, and packaging checks on pull requests.
- Test the minimum supported Python version and the primary development version; expand the matrix when compatibility requirements justify it.
- Install from the committed lockfile and use minimal CI permissions. Pin third-party actions to reviewed commit SHAs and maintain those pins.
- Keep changes focused. Explain the behavior changed, why it changed, and how it was validated.
- Document public API changes and configuration requirements. Use deprecation paths when downstream users depend on existing behavior.
- Review dependencies regularly and investigate security findings in context.

## Cloud development workflow

Use the existing checkout in the isolated cloud task. Do not create an additional Git worktree unless explicitly requested. Keep installation steps repeatable and separate retained dependencies from services that must restart. Document service startup and functional readiness checks when services are introduced.

## Definition of done

A change is complete when its behavior is implemented, relevant tests execute and pass, required quality and packaging checks pass, documentation reflects public changes, and any skipped checks or known limitations are stated explicitly.
