# Invest

This repository is the starting point for a Python project. Application code, package configuration, and tests have not been added yet.

## Development guidelines

Read [Python Development Guidelines](PYTHON_GUIDELINES.md) for the recommended project structure, extensibility practices, dependency management, coding standards, and testing workflow.

The recommended foundation is a `src/invest` package, a `pyproject.toml` configuration, a committed dependency lockfile, and pytest tests under `tests/`. Use Ruff for formatting and linting, and mypy for type checking.

## Getting started

1. Choose a supported Python version and declare it in `pyproject.toml`.
2. Add the package, runtime dependencies, and development tools using the selected dependency manager; the guidelines recommend `uv`.
3. Add tests alongside the first application behavior.
4. Document the actual installation, execution, and validation commands here once implemented.

There are currently no application startup commands or executable test suites. The commands in the guidelines describe the intended future workflow.

## Local files

The `.gitignore` excludes virtual environments, Python caches, build outputs, coverage reports, and local environment files. Keep credentials out of Git. A sanitized `.env.example` may be committed to document required configuration; dependency lockfiles should also be committed.
