# Invest

This repository contains the designs for three independent Python components in two top-level folders on `main`. Application code, package configuration, and tests have not been added yet.

## Components

- [Data preparation](data-pipeline/data-preparation/README.md): download, clean, preprocess, and publish CSV or SQLite datasets.
- [Strategy evaluation](data-pipeline/strategy-evaluation/README.md): apply trading rules to supplied data/signals and evaluate portfolio performance after costs.
- [Data mining framework](data-mining-framework/README.md): consume published datasets for factor discovery, model training, inference, and signal diagnostics.

The components exchange artifacts through a [versioned dataset contract](docs/DATA_CONTRACT.md). They do not depend on each other's private implementation; any shared public contract/runtime utility must have an explicit versioned interface. Each component will contain its own Python package, dependency configuration, and tests. See the [architecture guide](docs/ARCHITECTURE.md) for the folder layout and ownership boundaries.

## Development guidelines

Read [Python Development Guidelines](PYTHON_GUIDELINES.md) for the recommended project structure, extensibility practices, dependency management, coding standards, and testing workflow.

Read [Git Development Guidelines](GIT_GUIDELINES.md) for branch naming, focused commits, pull requests, history management, conflict resolution, and safe collaboration.

Read [Design by Contract Guidelines](DESIGN_BY_CONTRACT.md) for preconditions, postconditions, invariants, failure guarantees, boundary validation, numerical contracts, and interchangeable implementation tests.

The shared [quantile analysis](docs/QUANTILE_ANALYSIS.md) and [reporting](docs/REPORTING.md) specifications cover bucket comparisons, visualization ownership, and generated artifacts. The architecture guide lists the prerequisites for the first runnable end-to-end workflow.

Within each component folder, use a `src` package layout, a `pyproject.toml` configuration, a committed dependency lockfile, and pytest tests under `tests/`. Use Ruff for formatting and linting, and mypy for type checking. Adapt the single-package examples in the guidelines to each component's package name and working directory.

## Getting started

Start with the [roadmap](ROADMAP.md) for milestone sequencing and acceptance gates, and [TODO list](TODO.md) for actionable tasks and progress. The current next milestone is **M0: finalize financial contracts and the initial market/use case**. Python packages, CI, download adapters, mining algorithms, and simulation remain planned.

The first runnable milestone will publish a small dataset, apply one known causal formula, export frozen signals, and evaluate one fixed bucket strategy with reconciled accounting and saved reports. Advanced search methods follow verified returns, statistics, and robustness checks.

There are currently no application startup commands or executable test suites. The commands in the guidelines describe the intended future workflow.

## Documentation maintenance

Update this README with changes to project status, supported capabilities, layout, prerequisites, and actual installation/execution/check commands. Keep detailed task progress in [TODO.md](TODO.md) and milestone acceptance in [ROADMAP.md](ROADMAP.md); update affected component READMEs in the same change. Mark work complete only with implementation and validation evidence. See the [maintenance checklist](TODO.md#updating-the-backlog-and-readme).

## Local files

The `.gitignore` excludes virtual environments, Python caches, build outputs, coverage reports, and local environment files. Keep credentials out of Git. A sanitized `.env.example` may be committed to document required configuration; dependency lockfiles should also be committed.
