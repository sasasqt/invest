# Reproduce permitted static checks

Audited source: 90b5ca038155b97833b120baa57dfecd05d6f641; expected tree9b48fbc155c6f5006969241585f48953f63e809e.
Acquire source using approved GitHub access. Verify all110 blobs with remote-manifest.json, including uv.lock, saved-result and binary bytes. No raw vendor observations exist in this manifest. Do not run source modules to inspect them.

The supplied static_checks.py uses the standard library only: AST/TOML/JSON parsing, Git blob hashes and bash -n. Its original workspace layout is a source/ directory beside the script and remote-manifest.json; outputs go to outputs/audits/gpt/2026-10-31-repro/static-checks.json beneath that directory. Place verified source bytes there before running `python3 static_checks.py`. Do not treat parsing as semantic or behavioral correctness.

Repository execution remains BLOCKED until an existing enforced filesystem boundary passes outside-tree harmless-sentinel and denied-operation tests. Both available namespace launchers failed before a boundary existed; no sentinel-denial pass is claimed. No wrapper was substituted.

After isolation passes: exact locked setup, uv lock --check, all6 CI jobs, branch-coverage JSON and slowest25 tests, hashseed12345 repeat, published-boundary synthetic workflow, every required format and semantic hash gate, installed wheels/independence, then independent reproductions twice+controls and software benchmarks. Keep publishing credentials outside. Consult checkpoint.json for precise remaining work. Never run historical_workflow.sh with its default committed ledger; use a temporary authorized ledger and only an already-inspected licensed pre2025 snapshot. A manifest is not that snapshot.

Verification records contain independently derived synthetic inputs and expected values. They are static reasoning, not observed repository outputs. Research experiment definitions are in research/candidate-specifications.json. No script implements a product fix.
