"""Saved-results attribution (repo audit 2026-11-15): the signals bundle of the same replay
written at c6f2961 (before #39) and at main differ only in content_sha256 because scores of
-0.0 are now stored as 0 (DATA_CONTRACT.md "Serialization rules"); main must still read the
older bundle (bundle.py `_legacy_hash_matches`).
usage: python -I ra_signed_zero_legacy_read.py <old signals bundle> <new signals bundle>
Exit 0 when: the old bundle holds negative zeros, main's read_bundle accepts it, the new bundle
holds none, and both frames carry equal scores (with -0.0 == 0). Exit 1 otherwise."""
import json, math, sys
from pathlib import Path
import pandas as pd
from invest_data.bundle import read_bundle

old, new = Path(sys.argv[1]), Path(sys.argv[2])
raw_old = pd.read_parquet(old / "data.parquet"); raw_new = pd.read_parquet(new / "data.parquet")
neg = lambda s: int(sum(1 for v in s if isinstance(v, float) and v == 0 and math.copysign(1.0, v) < 0))
n_old, n_new = neg(raw_old["score"]), neg(raw_new["score"])
h_old = json.loads((old / "manifest.json").read_text(encoding="utf-8"))["content_sha256"]
h_new = json.loads((new / "manifest.json").read_text(encoding="utf-8"))["content_sha256"]
print(f"old bundle: {len(raw_old)} rows, negative-zero scores {n_old}, content_sha256 {h_old[:12]}")
print(f"new bundle: {len(raw_new)} rows, negative-zero scores {n_new}, content_sha256 {h_new[:12]}")
ok = True
try:
    _, f_old = read_bundle(old); print("main read_bundle(old): accepted (legacy hash path)")
except Exception as exc:  # noqa: BLE001 - report any refusal
    print(f"main read_bundle(old): REFUSED: {exc}"); ok = False; f_old = None
_, f_new = read_bundle(new); print("main read_bundle(new): accepted")
if f_old is not None:
    keys = ["decision_date", "instrument"]
    a = f_old.sort_values(keys).reset_index(drop=True); b = f_new.sort_values(keys).reset_index(drop=True)
    same = a[keys].astype(str).equals(b[keys].astype(str)) and bool(((a["score"] == b["score"]) | (a["score"].isna() & b["score"].isna())).all())
    print(f"scores equal (with -0.0 == 0): {same}"); ok &= same
ok &= n_old > 0 and n_new == 0 and h_old != h_new
print("RESULT:", "attributed: only the signed-zero storage rule changed the hash; the old bundle stays readable" if ok else "NOT as described")
sys.exit(0 if ok else 1)
