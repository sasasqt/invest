# Decisions carried between runs (user decides; the run never resolves these itself)

| Date raised | Decision | Options | Run's note | Status |
|---|---|---|---|---|
| 2026-10-31 | Universe equal-weight benchmark and delisting settlements (BH-2026-10-21-2 = GA-2026-10-31-2) | (a) settlement-inclusive benchmark; (b) keep price-only and label it in metrics.json and the report | The hunt classes the omission as a defect (medium); GPT asks for the policy first. Until decided, IR, alpha and beta of a `--delistings` run carry survivorship bias. | open |

## 2. Audit tooling and CI intent (2026-10-31, open)
- `bench.py` and `compare_record.py` compare `.gz` files by bytes; that turned the gzip MTIME of `quantiles/tables/*.csv.gz` into candidate C5, which verifier B dropped (the repository promises content hashes only). Owner thread: compare `.gz` by decompressed content or keep the hash exclusion. Recommendation RA-2026-10-31-8 (P3) offers `mtime=0` on the repository side.
- Whether the independent-install job should mean a consumer-style install (`uv pip install --no-sources`; candidate C4 dropped by verifier B, recommendation RA-2026-10-31-9, P3): user decides.
