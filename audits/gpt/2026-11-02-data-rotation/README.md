# Monday static evidence

Product source is not copied into this evidence folder. Materialize only permitted textual paths at source commit9913f94b9b795bd9633a6a683e9f420301e400b3 under a sibling `source/` directory before running check_static.py. Use the included main-tree.json and Git blob hashes; do not use inherited product files on the audit-output branch. The script reads source as text/AST and imports no project code. It generates specification expectations, not product-runtime results.

Reviewer2 working copies current-TODO.md/current-mining-cli.py correspond to canonical TODO.md and data-mining-framework/src/invest_mining/cli.py at that same source commit; their byte identities were checked. They are not republished. Full PR API payloads are omitted; compact triage is in open-prs.json. No raw market/vendor data, committed research ledger or reserved observations are needed.

The initial durable marker started.json intentionally retains its original started status. Terminal run state is result.json and the maintained checkpoint.json. A started marker alone is not proof of liveness.
