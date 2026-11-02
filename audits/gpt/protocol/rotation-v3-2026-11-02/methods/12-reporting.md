#### 12. Deliver the report and reproducible evidence

Prepare a dated report and a compact evidence bundle outside the preserved product checkout. Sanitize and publish only eligible outputs under section 14:

- `audit-report.md`: conclusion, audited SHA, scope/coverage, assumptions, priority findings, consistency matrix, validation results, benchmarks, limitations and next actions.

- `coverage.csv`: all tracked files and inspection status.

- `findings.json`: structured findings with stable IDs, evidence and status history.

- `validation.csv`: each check's command, environment, revision, outcome, counts, duration and evidence path.

- `benchmarks.csv` and `benchmark_samples.csv`: summaries and every raw measurement.

- `benchmark_inputs.json`: workload definitions, seeds, settings, input hashes and environment metadata.

- Audit-only reproduction and benchmark scripts, plus relevant sanitized logs.

- `checkpoint.json`: revision, completed work, remaining work, durable evidence locations and safe resume instructions.

Maintain the repository-facing layout under `audits/gpt/`: `\<date>.md` (use `-2`, `-3`, etc. for another report on the same date), `findings.md`, `recommendations.md`, `findings.json`, `coverage-map.json`, `coverage-map.md`, `coverage.csv`, `cross-check.md`, `exploration.json`, `overlap.csv`, `validation.csv`, `benchmarks/raw.jsonl`, `benchmarks/history.md`, permitted benchmark summaries/metadata, `\<date>-repro/`, `research/scouting-\<date>.md`, `research/papers.jsonl`, `research/ideas.md`, `research/experiments.jsonl`, `research/backlog.md`, `research/state.json`, `checkpoint.json` and `state.json`. Keep large intermediate outputs and full logs outside Git; commit only concise sanitized evidence and generators/check scripts that contain no raw data. Each committed file must be no larger than 5 MB. Read existing `decisions.md`; preserve genuine user changes and never invent user decisions.

Write saved checks first, then findings/recommendations, coverage and benchmark/cross-check/research history, the dated report, checkpoint, and state.json last. State includes last audited SHA/date/run ID, per-step status/evidence, peer revision and finding fingerprints, current reading split and four-run yields, persistent pending_second_review and open_places plus their resolution history, and the separate research cutoffs, query history, candidate IDs and experiment status. Persist completed work after each step. Publication is an idempotently recorded step; preparation is not proof of remote success. Keep dated observations, raw timing samples, installed graphs and runtime health in versioned evidence/state files rather than appending historical status overrides to these instructions. Never edit the routine's own instructions/settings during an unattended audit; propose changes for the user instead.

Do not include credentials, raw licensed vendor data, reserved observations, or unnecessary large intermediates. Persist the report and evidence through the available artifact mechanism; report any save failure and keep the recoverable output accessible.

The opening summary must say:

- What was actually covered and what remains.

- How many verified defects, unverified concerns and optional improvements were found.

- Whether the full test suite and required workflows completed, with results.

- Which bottlenecks or regressions were measured, or why no comparison was possible.

- The three to five most useful next actions, ordered by impact.

- Cross-check verdicts, unavailable peer evidence and unresolved disagreements.

- This run's separate repository-review and research-scouting exploration/exploitation splits, their measured yields and next-run allocations.

- Research papers screened, genuinely new strategy/method candidates, experiments actually run and the most useful next research action; distinguish untested hypotheses from exploratory results.

The report includes Summary; Cross-check with Claude; Exploration and exploitation; Dedicated research scouting; Red checks; Findings; Consistency matrix; Test matrix; Saved results; Benchmarks; Coverage map; Recommendations; Overlap with other routines; Still open; Dropped candidates; Health; Decisions needed; and actual validation commands/results. The test matrix distinguishes local and same-SHA GitHub results. Health lists missing tools, unavailable checks, fallbacks, assumptions and actual model/effort/usage when exposed. Publication status includes the exact audit-branch commit link or a clear unpublished result.

Choose one overall conclusion:

- **Action needed:** verified material problems were found.

- **No material issues found within the audited scope:** completed checks support that limited conclusion.

- **Audit incomplete:** missing coverage or evidence prevents a reliable repository-wide conclusion. Still list any verified material findings prominently.

If no new issues were found, include a brief dated statement saying so, the audited SHA, actual validation scope and limitations. Do not claim the repository is bug-free.

