# Data pipeline

This folder contains the [data preparation](data-preparation/README.md) component: download, validate, clean, and publish versioned datasets (CSV, SQLite, or Parquet bundles) for market bars, universe membership, point-in-time fundamentals, and signals.

[Strategy evaluation](../strategy-evaluation/README.md) is a separate top-level component, and training and inference live in [`data-mining-framework/`](../data-mining-framework/README.md). Preparation performs only deterministic transformations; learned preprocessing is fitted in mining training.

Read the [component architecture](../docs/ARCHITECTURE.md) for ownership and boundaries, and the [dataset contract](../docs/DATA_CONTRACT.md) for the exchange format. Follow the [Python guidelines](../PYTHON_GUIDELINES.md), [Git guidelines](../GIT_GUIDELINES.md), and [CI/CD guidelines](../CI_CD_GUIDELINES.md).
