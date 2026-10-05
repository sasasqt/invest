# Data pipeline and strategy evaluation

Both components are currently at the design stage. Follow the shared [roadmap](../ROADMAP.md) and [TODO list](../TODO.md) for implementation order and progress.

This folder contains two independent subprojects:

- [Data preparation](data-preparation/README.md): download, validate, clean, preprocess, and publish versioned CSV or SQLite datasets.
- [Strategy evaluation](strategy-evaluation/README.md): evaluate supplied trading rules and signals using consistent portfolio, execution, cost, and reporting logic.

The parent folder is an organizational container. Each subproject will have its own Python package, dependency configuration, lockfile, and tests. Each runs without importing another component's private implementation; optional public contract/runtime adapters require an explicit interface. Executable code has not been added yet.

Read the [component architecture](../docs/ARCHITECTURE.md) for ownership, proposed package layouts, contracts, and testing boundaries. The existing [dataset contract](../docs/DATA_CONTRACT.md) defines data exchange; fitted-model, signal, and strategy contracts remain to be implemented.

Training and inference belong in `data-mining-framework/`. Preparation performs deterministic transformations; learned preprocessing is fitted in mining training. Trading strategies belong in strategy evaluation, while factor-search strategies belong in mining.

Follow the [Python guidelines](../PYTHON_GUIDELINES.md) and [Git guidelines](../GIT_GUIDELINES.md). Keep components independently installable and validate their artifact interfaces with integration tests when implementation begins.
