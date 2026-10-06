# Rapid Software Development Guidelines

Develop quickly by shortening the path from a concrete requirement to working, verified behavior. Use small increments, reusable tooling, and fast feedback. These practices complement the [Python](PYTHON_GUIDELINES.md), [Git](GIT_GUIDELINES.md), and [design-by-contract](DESIGN_BY_CONTRACT.md) guidelines; they do not imply that the planned application or CI already exists.

## 1. Pick a small outcome

- Select a task from [TODO.md](TODO.md) that advances the current [roadmap](ROADMAP.md) milestone or resolves a blocking uncertainty.
- Describe observable acceptance criteria before coding: inputs, expected outputs, failure behavior, and a representative example.
- Prefer a small complete workflow over completing every layer or interface in advance. For this repository, a fixture dataset → known formula → frozen signals → reconciled strategy report is the first runnable target.
- Limit work in progress. Finish and validate one coherent change before starting unrelated features; make dependencies explicit when work can proceed independently.
- Split a task when it cannot be reviewed or verified as a focused change. Avoid mixing a feature, a broad refactor, and dependency upgrades.

## 2. Resolve uncertainty early

Use a bounded exploratory experiment when an API, numerical method, source format, or performance constraint is unclear. Define the question, the evidence needed, and the effort limit before starting. On reaching the limit, record the result and decide whether to implement, investigate further, or defer.

Keep prototypes separate from supported APIs. Reuse them only after addressing contracts, failure paths, dependencies, and validation. Notebooks can help exploration, but production behavior belongs in importable modules with thin command entry points. Persist useful findings and small reproducible examples; avoid keeping speculative scaffolding.

## 3. Use a short implementation loop

1. Read the affected code, contracts, and tests; check the working tree and identify existing behavior to preserve.
2. Implement the smallest useful behavior using simple functions and explicit dependencies. Add an abstraction when a concrete second implementation or variation needs it.
3. Add meaningful checks for the changed behavior. For a bug, first reproduce it and add a regression test when appropriate.
4. Run the fastest relevant checks while editing; use failures to refine the change.
5. Run all required checks for the affected scope before integrating. Review the diff and update public documentation and task status.
6. Commit a coherent, working increment; push or integrate under the agreed repository workflow. Follow [Git guidelines](GIT_GUIDELINES.md) and the user's branch instructions.

A small increment must remain correct for its declared scope. Explicitly unsupported behavior is preferable to silently producing misleading results.

## 4. Build a fast, trustworthy feedback loop

- Use the same formatter, linter, type-checker configuration, and locked dependencies locally and in CI.
- Keep ordinary tests deterministic and independent of live network access. Use small fixtures and temporary files; put live source checks in an explicit separate category.
- Run targeted tests during development, then the required component checks and affected integration checks before completion. Do not present targeted success as full validation.
- Exercise independent adapters against shared contract fixtures. Check installed packages and entry points when packaging behavior changes.
- Investigate flaky tests and slow checks. Measure durations before adding parallelism or caches; ensure caching cannot hide stale schemas, data, or artifacts.
- Make common setup and check commands repeatable once tooling exists, and document the exact commands in component READMEs. Avoid maintaining separate local and CI procedures.
- Do not add tests that only repeat implementation details or invent an application test suite for a documentation-only change. Documentation changes need link, example, and whitespace validation as applicable.

Fast checks support frequent feedback; they do not replace required acceptance gates.

## 5. Match validation to the consequence of failure

| Change | Useful validation |
|---|---|
| Documentation or local formatting | Relevant links, examples, whitespace, and diff review |
| Pure transformation or numerical routine | Reference examples, boundaries, invalid inputs, and relevant properties |
| Public schema or storage adapter | Compatibility fixtures, round trips, independent readers, and version handling |
| Timing, training splits, or inference | Causality, leakage prevention, frozen export/reload parity, and provenance |
| Execution or accounting | Hand-calculated ledgers, reconciliation, costs, external flows, and failure paths |
| Cross-component workflow | Artifact-only integration and independent package execution |

Do not add indiscriminate checks to every inner loop. Validate at boundaries and reuse established invariants where safe. Essential production checks must remain active under `python -O`.

## 6. Keep changes easy to integrate and reverse

- Use small focused commits and review changes while context is fresh. Integrate frequently enough to expose incompatibilities early.
- Preserve supported public contracts. Stage an incompatible change through explicit versioning, migration, and fixtures rather than silently changing both sides.
- For persistent outputs, validate before atomic publication. A failed experiment must not leave a partial bundle that consumers treat as valid.
- Keep optional experimental algorithms behind explicit configuration or a narrow interface when needed. Remove abandoned experiments and temporary switches.
- Choose maintained dependencies for demonstrated needs; check compatibility and lock them. Avoid building infrastructure already adequately provided by a library.
- Record consequential tradeoffs briefly near the design they affect. Create larger decision records only when alternatives or long-term consequences justify them.

## 7. Control technical debt and scope

When deferring work, record a specific TODO with its impact, dependency, and completion criterion. A bare “fix later” comment is not enough. Address debt when it blocks the next increment or creates repeated failures; reserve broad cleanup for a focused change.

Profile representative workloads before optimizing. Record workload, baseline, correctness checks, and measured improvement. Avoid adding services, plugin systems, distributed execution, dashboards, or multiple storage formats before the baseline demonstrates a need.

Observe development friction through failed checks, time to a verified change, flaky tests, and recurring manual steps. Use these observations to improve the workflow; commit counts and lines of code are not progress measures.

## 8. Use assistants and generators with verification

Give tools a bounded task, relevant interfaces, and observable acceptance criteria. Review generated diffs, dependencies, and commands. Verify behavior with independent expectations rather than relying on generated tests that reproduce the same mistake. Inspect for accidental credentials, unsupported APIs, and unnecessary code before committing.

The contributor integrating the change remains responsible for its correctness and documentation. Do not treat generated explanations or passing narrow tests as evidence that a financial claim is valid.

## 9. Preserve research validity while iterating quickly

Small datasets and short runs accelerate debugging. Label them as development evidence; they cannot establish statistical robustness, capacity, or profitability.

- Keep development feedback separate from frozen confirmation. Repeatedly inspecting a holdout turns it into development data.
- Capture datasets, configurations, versions, seeds, budgets, and unsuccessful trials automatically as experiment tooling is implemented.
- Keep factor diagnostics separate from executable portfolio performance; use the [alpha validation protocol](data-mining-framework/ALPHA_VALIDATION.md) and [metric specification](strategy-evaluation/METRICS.md).
- Confirm causality and accounting before expensive algorithm comparisons. Add complexity only after a reliable baseline is available.

## 10. Finish each increment

An increment is complete when its acceptance criteria are met, required checks pass, and the diff is reviewed. Update the README when capabilities, status, setup, or commands change; update affected component READMEs and [TODO.md](TODO.md) in the same commit. Update [ROADMAP.md](ROADMAP.md) when milestone scope or acceptance changes.

Record material limitations and unrun checks accurately. For a requested push, verify the intended branch and a clean or explained working tree afterward. Working software and trustworthy evidence establish progress; documentation must describe that actual state.
