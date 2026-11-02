#### 10. Evaluate improvement opportunities

Rank improvements by practical benefit, supporting evidence, effort, dependencies and risk. Consider:

- Correctness and stronger shared contracts.

- Faster or less memory-intensive operations with measured bottlenecks.

- Better failure messages, diagnostics and recoverability.

- Simpler architecture and removal of harmful duplication.

- Clearer public APIs, installation, CLI defaults and documentation.

- Targeted test gaps, CI portability, packaging and reproducibility.

- Research controls that prevent invalid statistical or financial claims.

- Research-informed methods and strategy experiments from section 15, with literature evidence, repository fit and local validation status kept distinct. A promising paper is a research candidate, not an implemented improvement or confirmed trading edge.

Do not label personal style preferences, broad rewrites, speculative abstractions or unsupported features as defects. Do not recommend new dependencies, databases, caching layers or concurrency without explaining the problem and how to verify the benefit.

Add at most three optional new recommendations per daily run and seven per rolling seven Berlin dates; refresh existing ones whose evidence changed. Report all verified defects and unfavorable material observations regardless of these recommendation caps. P1: correctness, misleading evidence labels or red required checks. P2: reproducibility, CI parity, untested decision code and default-workflow regressions. P3: lower-impact hygiene, speed improvements elsewhere and refactors. Keep refactors behind delivering a correct, reliable main branch; recommendations do not authorize implementation.

Use effort estimates S (up to about two hours), M (up to about a day), or L (larger/cross-component or contract work), with likely files and runnable acceptance checks. Assign a logical owner or "user decides" without contacting that owner. Before adding a row, consult accessible backlog, roadmap, related PRs and other routine ledgers; retain existing identifiers and add only new evidence for an already tracked root cause.

Measure overlap with accessible other routines in `overlap.csv`: date, check/lens/case, minutes, findings, already-known findings, unique findings, and any twin check on the same inputs in the last seven days. Count shared findings by root cause in both directions. An unavailable, inactive or non-comparable routine is not a zero-overlap observation. After two comparable runs, propose keep/move/drop per check under Decisions needed, considering cadence and unique findings. Two runs are a small sample; a check finding nothing anywhere remains under observation for at least four comparable runs. Do not change any other routine or silently drop this audit's required coverage.

