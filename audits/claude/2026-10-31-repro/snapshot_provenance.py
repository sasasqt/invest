#!/usr/bin/env python3
"""Verify every raw file listed in a snapshot's snapshot.json against its recorded sha256. Usage: snapshot_provenance.py <snapshot dir>"""
import hashlib, json, pathlib, sys
snap = pathlib.Path(sys.argv[1]); meta = json.load(open(snap / "snapshot.json")); bad = n = 0
for sym, info in meta["files"].items():
    p = snap / info["path"] if "path" in info else snap / "raw" / f"{sym}.json"
    if not p.exists(): print("MISSING", sym, p); bad += 1; continue
    h = hashlib.sha256(p.read_bytes()).hexdigest(); n += 1
    if h != info["sha256"]: print("MISMATCH", sym, h[:12], info["sha256"][:12]); bad += 1
print(f"checked {n} raw files against snapshot.json sha256: {bad} problems"); sys.exit(1 if bad else 0)
