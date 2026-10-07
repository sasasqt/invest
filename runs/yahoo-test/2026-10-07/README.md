# Yahoo test run, 2026-10-07

Saved outputs of `scripts/historical_workflow.sh` on test-only Yahoo Finance data, 2010-01-01 to 2024-12-31. The results and their limitations are discussed in [the historical baseline](../../../docs/HISTORICAL_BASELINE.md#verdicts-on-the-current-code-2026-10-07). This run is **survivorship-biased** and exploratory: it is not alpha evidence.

## Provenance

- Raw snapshot downloaded 2026-10-07T10:32:52Z, then replayed offline on a clean checkout of `c6f2961` (recorded as `code_revision` in [eval/manifest.json](eval/manifest.json)). The replay published the same dataset hashes as the run on the downloaded copy.
- Market bundle `content_sha256` `1fc2a8037ffe0674986adf07491ef6f89df765b135c10e94bec68edaff441129`; SPY `02cd765d1fb1b02cfa24587d07fd2dc7083caee3d8fa2c865f7b3b5878b7cf6c`.
- The confirmation-use ledger was a temporary copy, so [ledgers/yahoo-test.jsonl](../../../ledgers/yahoo-test.jsonl) is unchanged and 2025 onward is still reserved.

## What is here and what is not

| path | content |
|---|---|
| [snapshot/snapshot.json](snapshot/snapshot.json) | Snapshot manifest: request, retrieval time, per-symbol file SHA-256 and the SNDK failure |
| `data/*/manifest.json` | Market and SPY bundle manifests (schema, metadata, provenance, content hashes) |
| `mining/` | Frozen factor and full-sample factor diagnostics (`daily_ic.csv`, tail returns, figures) |
| `signals/manifest.json` | Signals bundle manifest |
| `eval/` | Backtest [report](eval/report.md), [verdict](eval/verdict.json), metrics, statistics, resolved config, scenario table and figures |

Not committed: the raw Yahoo responses, the published Parquet bundles, the decile return table and the daily, trade and episode ledgers (about 65 MB in total). They are vendor data or are rebuilt exactly by replaying the snapshot. A compressed copy of the raw snapshot is kept outside the repository; its files must match the SHA-256 values in `snapshot.json`. To rebuild everything, unpack it and run `SNAPSHOT=<dir> uv run scripts/historical_workflow.sh <out>`.
