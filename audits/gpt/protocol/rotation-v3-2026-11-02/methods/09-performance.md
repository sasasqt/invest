#### 9. Benchmark software performance reproducibly

Separate **software benchmarks** (time, memory, throughput, storage and scaling) from **investment benchmarks** (returns relative to a financial comparator). This section concerns software performance.

Before measuring, define workloads, sizes, seeds, settings, correctness checks, baseline and measurement budget. Do not select favorable inputs after inspecting timings.

Suggested starting workloads, adjusted to the actual APIs and available resources:

| Workload | Measurements and correctness gate |
|---|---|
| Bundle validation, publication and reads | CSV/SQLite/Parquet wall time, rows/second, peak memory, disk size; equivalent logical content |
| Point-in-time joins and expression evaluation | Throughput and scaling with instruments, sessions and lookbacks; causal and numerical agreement |
| Factor diagnostics and fixed-budget search | Time and memory versus horizons, candidates and resamples; equal trial budgets and output semantics |
| Strategy evaluation and stress scenarios | Sessions/second or instrument-decisions/second, memory and scaling; accounting reconciliation |
| Quantile and tail portfolios | Growth with portfolio count and history length; unchanged membership and return definitions |
| Reporting and run recording | Table/figure generation time, output size, compression and recovery; complete byte or semantic recovery as required |
| Complete offline workflow | End-to-end time, peak resource use and artifact consistency |

Use deterministic synthetic panels. Initial size tiers may be 25 instruments × 250 sessions, 100 × 1,000, and 500 × 6,000, with the largest tier subject to resource limits. These are candidate workloads, not a mandatory Cartesian product of every stage, format and size. Calibrate a small case first, then select larger cases that fit the predeclared time and memory budgets. Add a long-history/smaller-universe case to isolate report-size and recorder behavior. These are measurement fixtures, not investment recommendations.

Use the following repeatable workflow cases as the recurring core, verifying the script's actual defaults and recording every parameter. The earlier panel tiers remain optional targeted scaling cases; do not require both entire grids in one run.

| Case | Deterministic input | Measured repetitions after one recorded warm-up |
|---|---|---:|
| synth-S | 20 instruments, 300 sessions, 20 search trials | 7 |
| synth-M | Declared workflow defaults; initially 60 instruments, 750 sessions, 200 trials | 7 |
| synth-L | 120 instruments, 1,500 sessions, explicitly recorded trial budget | 3 |
| synth-XL | 240 instruments, 3,000 sessions; only if L's median is below 90 seconds and the resource budget permits | 1 exploratory measurement |
| formats | M-sized synthetic publication/read through CSV, SQLite and Parquet | 3 per format |
| historical replay | Matching authorized pre-cutoff snapshot, offline, temporary ledger | 1 exploratory measurement |
| full pytest | Reuse the test stage's duration and 25 slowest tests | 1, labeled not a quiet benchmark |

Historical timings supplied by the other audit are external observations, not this environment's measurements or a comparable baseline. A single XL or replay run has no measured repeatability and cannot support a precise regression claim.

Measurement rules:

- Record commit, lockfile hash, interpreter/library versions, OS, CPU, available RAM, CPU/memory limits, worker/thread settings, storage location, seeds and input hashes.

- Benchmark without test coverage, debugger or profiler overhead. Profile bottlenecks in a separate diagnostic run.

- State whether timings include process startup, isolation, instrumentation and supervisor overhead. Measure an empty-process/control workload where useful, without subtracting noisy overhead to manufacture a speedup.

- Separate data generation and installation from operation timings; also report them separately when operationally relevant.

- Distinguish startup and steady-state behavior. Label process-cold versus warm runs accurately; do not call the OS cache cold unless it was controlled. Do not seek privileged cache resets.

- Use a monotonic clock. Start with one warm-up and seven measured repetitions for short workloads; for expensive workloads use at least three when feasible and explain reductions.

- Save every measured sample, not just the fastest. Report median, spread, sample count, failures and timeouts. Use tail percentiles only when the sample count supports them.

- Measure peak resident memory in fresh processes with a tool covering native allocations; explain whether children are included. Python allocation tracking alone is not total process memory.

- Keep simultaneous workloads from contaminating timing comparisons. Run comparisons on the same host, inputs and environment, alternating order where practical.

- Use the last genuinely comparable audit or an explicitly selected older revision as baseline. Re-run both sides under matched conditions when possible. Without a comparable baseline, establish one and label change/regression claims unavailable.

- Report absolute values and relative differences with their direction. For example: `(current_time - baseline_time) / baseline_time × 100`; positive means slower. Describe noise and competing memory/runtime tradeoffs.

- A default 10% slowdown can flag investigation; it is not proof of a regression without repeatability and an effect larger than measurement noise. Prefer any repository-defined performance budget.

- Enforce per-case timeouts and declared memory ceilings where available. Save completed samples when a case exceeds its budget; label it timeout, resource-limited or blocked. Do not extrapolate unexecuted large-case results or treat an incomplete sample set as a precise performance estimate.

- Validate results after each benchmark. Faster wrong outputs, lower trial counts, fewer scenarios, weaker precision or missing records are not improvements.

Keep append-only `benchmarks/raw.jsonl` with run ID/date, case/repetition and warm-up status; audited SHA; CPU model/count/quota, RAM limit, kernel, interpreter, package and tool versions, thread settings and lockfile hash; all workload parameters and available input/snapshot hashes; exit status; wall and CPU seconds; process-tree peak RSS when actually measurable; per-stage durations; instrument-days/second and search trials/second; output bytes and file counts in total, by stage and by type. Mark unavailable measurements explicitly. Collect stage timings without verbose traces that could expose environment values.

Every repetition must pass a versioned semantic output gate against the equivalent warm-up. Inventory every output file and record its comparison method and digest; additions and removals participate. Parse JSON/JSONL and normalize only predeclared volatile creation/retrieval timestamps and output-root strings; preserve substantive values, identities, status, trial counts and record order. Never skip a whole ledger because its records contain timestamps. Decompress .csv.gz tables and compare their content, rather than excluding them because gzip headers vary. Compare plain CSV content; compare text with only declared normalization. Other formats require an explicit validated logical comparison or a disclosed conservative raw-byte check; never silently omit unknown artifacts. Require figures to exist and be nonempty and verify their source tables; record that rendered pixels are not compared. Corrupt/unreadable compared outputs fail the gate and their failed samples/reasons are retained. Hashing and inventory occur after timing. Save per-file manifests, gate version, exclusions and rationale with every sample. Retain original failures and samples, exclude incorrect/failed cases from speed medians, and regenerate history from the append-only ledger. Earlier measurements remain historical with their original narrower gate; never upgrade their equivalence claims or pool incompatible gate versions without a fresh matched run.

Use the median of up to the last four completed comparable runs as the reference, disclosing the count. Match hardware/runtime fingerprint, workload parameters, input identity and measurement method; if they differ, say not compared. With fewer than four prior comparable runs, flags are provisional until repeatability is established. Retain these screening rules, subject to measurement noise and independent confirmation:

- At least 10% slower and outside prior comparable run ranges: watch, not automatically a defect.

- Wall/CPU median at least 25% above reference and above the prior comparable maxima: benchmark candidate; initially low severity, potentially medium for the default workflow or a slowdown of at least twofold, depending on actual impact.

- Peak RSS at least 20% above a comparable reference: memory-regression candidate; confirm the measurement scope and cause.

- Synthetic output size changing by more than 1%: explain the writer/contract changes or mark the difference unexplained; it is not by itself proof of a bug.

- Estimate a log-log scaling slope `b` only with disclosed sizes, fit method and sample count. A value above 1.3 prompts investigation/recommendation, not a universal complexity claim. Hold trials and other settings constant for a data-size scaling experiment. If S/M/L also change the search budget, label the slope mixed-workload scaling and do not attribute it solely to data size.

Identify dominant bottlenecks using measurements and code traces. State complexity in terms of measured problem sizes where possible. Recommend optimizations with estimated effort and risk; call speedup claims unmeasured unless an equivalent alternative was actually measured.

Do not alter production code to benchmark a proposed fix. If no alternate implementation was tested, report the bottleneck and the experiment needed next.

