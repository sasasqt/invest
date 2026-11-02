#### 7. Add independent checks where evidence is missing

Write audit-only test and reproduction scripts outside tracked repository files. Prefer a few strong checks over many tests that restate the implementation.

Include relevant examples of:

- Hand-computed cash/position/cost/equity reconciliation and metric calculations.

- Future-data perturbation, prefix invariance and as-of revision checks.

- Stable tie handling, exact quantile cutpoints, orientation reversal, and small or missing cross sections.

- Format round trips and equivalent logical hashes across supported storage formats.

- Artifact export, reload and inference consistency.

- Invalid-input rejection without unintended files or ledger entries.

- Deterministic seeded replay with semantically equivalent outputs, accounting for documented timestamps.

- Report reconstruction from saved tables and consistency of statuses across outputs.

- Long histories and realistic output sizes that exercise recorder limits, compression and recovery.

Use property tests, randomized checks or fault injection only with fixed seeds, explicit budgets and a stated invariant. Do not assume two implementations are independent if they call the same underlying helper. Label unverified hypotheses separately.

