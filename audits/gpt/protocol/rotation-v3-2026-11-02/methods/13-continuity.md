#### 13. Make later runs cumulative and resumable

- Recheck current instructions and revision. Preserve stable finding IDs and link prior evidence to its original SHA and environment.

- Reverify unresolved findings and claimed fixes; do not accept a backlog checkbox or author statement as resolution evidence. Load persistent pending_second_review and open_places queues before selecting new discretionary work. Each pending_second_review item records a stable item/finding ID, kind, priority/impact, source/evidence fingerprint, evidence references, review status, next check, first/last queued time and deferral reason. Include proposed drops and materially disputed severity or interpretation. Prioritize carried material items before new items of comparable impact; preserve lower-priority items until explicitly reviewed or superseded with evidence. A passing check does not establish independent second review, and the same agent's second pass is not independent. Remove an active queue item only after recording its resolution and preserving its history; changed source requires scope revalidation, not blind reuse or deletion.

- Compare benchmark results only across comparable setups. A hardware or dependency change may require a new baseline.

- Refresh the whole coverage inventory. Prioritize changed files and affected consumers, but continue repository-wide review. Persist reviewers' concrete unchecked locations in open_places with stable ID, path/range or input, source fingerprint, risk/priority, originating reviewer/item, next invariant/check, queue age and deferral reason. Start the next exploitation selection with feasible high-impact queued places, alongside unresolved candidates and peer leads, without abandoning exploration. Credit a place as checked only with its exact scope and evidence; keep a resolution history. Initialize missing queues explicitly and migrate/reconcile existing backlog entries without losing them or inventing review history.

- Reuse unchanged evidence transparently; name its revision and date. Distinguish reused checks from newly executed ones.

- Do not duplicate known findings or reset research ledgers to obtain cleaner-looking results.

- Resume a partial audit from its checkpoint. If the branch has advanced, retain the old snapshot or explicitly start a new audit; never combine results from different SHAs into a single supposedly current verdict.

- Avoid overlapping runs and conflicting output writes. A partial report must remain available even if a later stage fails.

- Before delivery, recheck the default-branch SHA and state whether it advanced. The report remains about the immutable audited SHA.

- Use write-ahead per-step checkpoints: mark started before work, then done with revision-pinned evidence. Resume an unfinished run less than seven days old only while its saved immutable scope and artifacts are usable. Mark older/unusable runs superseded with the reason; preserve their reports rather than silently claiming they finished. Reconcile any potentially completed publication against the remote branch before retrying. Keep resource-limit checkpoints through exposed mechanisms; do not depend on private checkpoint scripts or unseen usage dashboards.

