# Invest

This repository contains the designs for two independent Python components on `main`. Application code, package configuration, and tests have not been added yet.

## Components

- [Data pipeline](data-pipeline/README.md): download, clean, preprocess, and publish CSV or SQLite datasets.
- [Data mining framework](data-mining-framework/README.md): consume published datasets for analysis, training, and evaluation.

The components exchange artifacts through a [versioned dataset contract](docs/DATA_CONTRACT.md). They do not import each other's code. Each folder will contain its own Python package, dependency configuration, and tests.

## Development guidelines

Read [Python Development Guidelines](PYTHON_GUIDELINES.md) for the recommended project structure, extensibility practices, dependency management, coding standards, and testing workflow.

Within each component folder, use a `src` package layout, a `pyproject.toml` configuration, a committed dependency lockfile, and pytest tests under `tests/`. Use Ruff for formatting and linting, and mypy for type checking. Adapt the single-package examples in the guidelines to each component's package name and working directory.

## Getting started

1. Choose a supported Python version and declare it in `pyproject.toml`.
2. Add the package, runtime dependencies, and development tools using the selected dependency manager; the guidelines recommend `uv`.
3. Add tests alongside the first application behavior.
4. Document the actual installation, execution, and validation commands here once implemented.

There are currently no application startup commands or executable test suites. The commands in the guidelines describe the intended future workflow.

## Local files

The `.gitignore` excludes virtual environments, Python caches, build outputs, coverage reports, and local environment files. Keep credentials out of Git. A sanitized `.env.example` may be committed to document required configuration; dependency lockfiles should also be committed.
