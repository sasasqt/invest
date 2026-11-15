"""open_place 4 (reviewer 2, 2026-11-08): a manifest.json whose storage.path holds a Windows
backslash ("data\\data.csv"), read on Linux. Does invest_data.bundle normalise, reject, or
read it? (DATA_CONTRACT.md: artifact paths are relative to the bundle root.)
Usage: uv run python ra_bundle_backslash_storage_path.py <tmp dir>"""
import json, sys
from pathlib import Path
import pandas as pd
from invest_data.bundle import BundleError, Column, read_bundle, write_bundle

tmp = Path(sys.argv[1]); tmp.mkdir(parents=True, exist_ok=True)
frame = pd.DataFrame({"record_id": ["a", "b"], "value": [1.5, None]})
cols = [Column("record_id", "string", nullable=False), Column("value", "float64", nullable=True)]
out = tmp / "bundle"
write_bundle(frame, out, dataset_id="x", columns=cols, primary_key=("record_id",))
m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
print("writer stores storage.path =", repr(m["storage"]["path"]))
for variant in ("data\\data.csv", "sub\\data.csv", ".\\data.csv"):
    m2 = dict(m); m2["storage"] = dict(m["storage"], path=variant)
    (out / "manifest.json").write_text(json.dumps(m2, indent=2) + "\n", encoding="utf-8")
    try:
        _, df = read_bundle(out)
        print(f"{variant!r}: READ {len(df)} rows (accepted)")
    except BundleError as exc:
        print(f"{variant!r}: refused: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"{variant!r}: OTHER ERROR {type(exc).__name__}: {exc}")
print("verdict: the writer always stores the fixed name without separators; a hand-edited backslash path is refused on Linux as a missing data file (no normalisation, no escape); on Windows the same manifest would read. Not a defect; a note for DATA_CONTRACT only if a reader must agree across platforms.")
