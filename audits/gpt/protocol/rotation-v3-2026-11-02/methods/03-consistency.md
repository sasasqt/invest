#### 3. Build a consistency matrix

For each important behavior, compare the specification, actual implementation, tests, CLI behavior, examples, saved artifacts and documentation. Record intended versus observed behavior, affected consumers, and authoritative evidence. Do not resolve contradictions by assuming that code or prose is always correct.

Check at least:

| Area | Questions to resolve |
|---|---|
| Component boundaries | Do preparation, mining and evaluation own the responsibilities described by the architecture? Are dependencies public and necessary? Can each package install independently? |
| Dataset contracts | Do writers and readers agree on schema versions, required fields, keys, ordering, types, units, calendars, timezones, hashes and failure behavior? |
| Storage | Do CSV, SQLite and Parquet preserve the same logical content and documented semantics? Are missing values, precision and categorical values handled consistently? |
| Time and availability | Do event times, publication/revision times, decision times, fills and label horizons align across stages? |
| Configuration and CLI | Do defaults, validation rules, flags, help text, examples and resolved configs agree? Are unsupported combinations refused clearly? |
| Statistics and accounting | Do reports use the metrics, timing, units and cost definitions implemented by the engine? |
| Artifact versions | Are migrations explicit? Are old artifacts either read correctly or refused with a usable migration message? |
| Documentation and progress | Do README, roadmap, backlog and component docs distinguish implemented, tested, planned and unsupported capabilities? |
| CI and packaging | Do documented commands match workflows? Do built packages contain and declare what their users need? |
| Saved results | Can reported figures be traced to their code, inputs, configs and evidence without treating historical results as current? |

Prioritize contradictions that can silently change financial results, accept invalid evidence, lose outputs, or break component contracts.

Check lockfile consistency with `uv lock --check` in check mode, without changing manifests or the lockfile. Compare each package's supported Python range with the actual CI interpreters, Ruff target, Mypy target and documented commands. Validate console entry points. Use an AST import inventory to identify possible undeclared or unused runtime dependencies, then verify the impact through independent installation before calling a dependency defect confirmed. Evaluation must remain independent of mining.

Inspect action SHA pins and version comments, minimal workflow permissions, same-SHA CI status, and failed/cancelled/retried main-branch runs from the last 30 days when accessible. Check every shell script with `bash -n`; inspect its error-handling settings and pipeline behavior. Do not source shell scripts during syntax checking.

