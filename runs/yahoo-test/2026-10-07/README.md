# Run record: yahoo-test-2010-01-01-2024-12-31

Saved by `scripts/save_run.py` from a `scripts/historical_workflow.sh` run. Test-only Yahoo data is survivorship-biased: read these results as exploratory, not as alpha evidence. See [eval/report.md](eval/report.md) for the full report.

## Provenance

| item | value |
|---|---|
| Snapshot retrieved | 2026-10-07T10:32:52+00:00 |
| Snapshot request | 2010-01-01 to 2024-12-31, 102 symbols; failed: SNDK |
| Code revision | `c6f29611fb4f3c9649ef188276666078130f96f0` |
| Market bundle | `1fc2a8037ffe0674986adf07491ef6f89df765b135c10e94bec68edaff441129` |
| Benchmark SPY | `02cd765d1fb1b02cfa24587d07fd2dc7083caee3d8fa2c865f7b3b5878b7cf6c` |
| Signals | `781cd92cbb3982dc1adffb4ecf95d31d692d77f5cc0a74be86a1ccf41c10d78c` (signals-f_f4031d273d5d) |
| Factor verdict | `not_confirmed` |
| Portfolio verdict | `inconclusive` (verdict version 2) |

## Not included

Raw vendor responses, published bundles and large ledgers are not committed. They are vendor data or are rebuilt exactly by replaying the raw snapshot, whose files must match the SHA-256 values in `snapshot/snapshot.json`: `SNAPSHOT=<dir> uv run scripts/historical_workflow.sh <out>`.

## Notes

The snapshot was downloaded on `4e439f0` and then replayed offline on a clean checkout of `c6f2961`, which published the same dataset hashes. The ledger was a temporary copy, so [ledgers/yahoo-test.jsonl](../../../ledgers/yahoo-test.jsonl) is unchanged and 2025 onward is still reserved. A compressed copy of the raw snapshot is kept outside the repository. Results are discussed in [the historical baseline](../../../docs/HISTORICAL_BASELINE.md#verdicts-on-the-current-code-2026-10-07).
