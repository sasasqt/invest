#### 8. Execute complete workflows

On an integration visit, select one bounded deterministic synthetic workflow case through actual published boundaries; rotate and queue the remaining combinations:

1. Prepare and publish market data, membership and fundamentals where supported.

2. Evaluate a predetermined formula; freeze it; export and reload signals.

3. Run the fixed strategy, quantile and tail portfolios, and relevant stress scenarios.

4. Generate reports and figures; save and recover the run record using temporary destinations and ledgers.

5. Reconcile input identities, configs, timing, outputs, statuses and provenance across the stages.

Exercise CSV, SQLite and Parquet where supported. Include normal, boundary, missing-data, invalid-input and long-history cases without attempting every possible combination blindly.

Run an offline historical replay only if an authorized, already-inspected snapshot is actually accessible. Preserve its input hashes and date selection. Compare the predetermined strategy with the repository's declared financial benchmark and saved baseline where the data support a like-for-like comparison. Align dates, currency, return basis, costs and exposure assumptions; label gross versus net differences explicitly. Do not tune strategies against these outcomes or present an exploratory replay as new confirmation. If the snapshot is unavailable, say so; synthetic checks do not establish historical investment performance.

Inspect saved records newest first, at most two historical records per selected integration visit, rotating older ones by their last-check date. Match an accessible, permitted snapshot to the record's original request and file hashes before replay. Missing snapshots are evidence gaps, not proven numerical defects. Replay once at the recorded code revision with its own locked environment and once at the audited main revision, using separate disposable clones and temporary ledgers, never additional worktrees.

Compare saved JSON/CSV strings and integers exactly and finite floats at relative tolerance `1e-12`, with zero absolute tolerance unless the contract explicitly requires another rule. Predeclare genuinely volatile keys such as creation timestamps. Preserve explicit statuses and reasons; require figures to exist and verify their source tables without demanding byte-identical renderer output. Attribute main-versus-record differences to concrete behavior changes and commits, not merely a commit touching the producer's path. Historical documentation may legitimately quote its historical revision; recommend re-recording only when a claim presented as current is stale or provenance is unclear.

Validate ledger JSON Lines and reservation handling without reading reserved observations. After tests, workflows and benchmarks, verify the audited source copy's tracked state and unignored files against its initial state. Distinguish an intentional, declared audit output from an unintended workflow side effect. Existing contributors' checkouts and research ledgers must remain untouched.

