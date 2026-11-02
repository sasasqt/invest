#### 2. Track coverage across the entire repository

Create `coverage.csv` and a persistent `coverage-map.json` with a row for every tracked file: path, content identity, component, category, line count, inspection depth, exact line ranges read, reviewer/producer, checks and lenses performed, evidence reference, audited SHA, status, last-review dates, and exclusion reason if applicable. Distinguish this run's work from earlier evidence and from the peer audit's work.

Use explicit statuses: `reviewed`, `partially_reviewed`, `checked_automatically`, `inventoried`, `blocked`, and `excluded_with_reason`. Reserve review credit for actual semantic inspection at the stated scope. Record executed behavioral checks separately; one check does not establish that all logic in its source file was reviewed. A passing suite, search hit, scan or inventory entry alone is not manual review.

- Inspect first-party source, tests, scripts, workflows, configuration and documentation. Review small files directly; map large modules by responsibility and review each responsibility and its callers.

- Inventory generated, binary, vendor and saved-result files too. Validate their provenance, schema, references and consistency as applicable; state when only metadata or a representative sample was examined.

- Cover unchanged modules and interactions across components. Do not impose the separate PR-review task's comment-count caps on this audit.

- Report file and component totals for each coverage status. If any in-scope logic remains unreviewed, use the conclusion `Audit incomplete` and identify it precisely.

- Render per-category file/line totals, review coverage over the last 28 days, never-reviewed files, available per-file test line/branch coverage, the ten least covered files, this run's reading slice and the next slice. Give GPT-only and either-audit coverage separately. Unknown or incompatible peer coverage is unknown, not zero or proof of review. A changed file's old coverage is evidence about the old content only.

