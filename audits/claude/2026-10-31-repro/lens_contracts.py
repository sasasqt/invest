#!/usr/bin/env python3
"""Contracts lens (repo audit 2026-10-31): published bundles against docs/DATA_CONTRACT.md.

Usage: python3 -I lens_contracts.py <workflow out dir> [<out dir> ...] [--formats DIR DIR ...]

For every bundle (a directory holding manifest.json with contract_version) under each out dir:
  C1 the storage file exists, its format is csv/sqlite/parquet, stored column names == manifest column names (order too)
  C2 row_count == stored rows
  C3 non-nullable columns hold no null; primary key non-null and unique
  C4 content_sha256 recomputed from the stored rows == manifest value
  C5 every 64-hex value in any JSON file under the out dir (other than a manifest's own content_sha256)
     is the hash of a bundle in the same out dir (upstream references resolve)
  F1 --formats: bundles at the same relative path in each DIR share content_sha256 and hold equal rows
Reading is independent of invest_data: pyarrow for parquet, the csv module with the contract's null token and
escape rule for CSV, sqlite3 read-only for SQLite. The contract (DATA_CONTRACT.md, "Optional v1 extensions")
says only "a format-independent hash of the column schema and canonical row values"; the canonical form used here
is the one bundle.py documents in code (sorted-key JSON of the column list, then one compact JSON line per row with
dates as ISO strings and \n after each row). Exit 1 on any FAIL.
"""
from __future__ import annotations
import csv, datetime as dt, hashlib, json, os, re, sqlite3, sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
fails = 0

def out(status, name, detail=""):
    global fails
    if status == "FAIL": fails += 1
    print(f"{status} {name}: {detail}")

def conv(value, typ):
    if value is None: return None
    if typ == "date": return dt.date.fromisoformat(str(value)) if not isinstance(value, dt.date) else value
    if typ == "float64": return float(value)
    if typ == "int64": return int(value)
    if typ == "boolean":
        if isinstance(value, bool): return value
        if isinstance(value, int): return bool(value)
        return {"true": True, "false": False}[str(value)]
    if typ == "timestamp":
        if isinstance(value, dt.datetime): return value
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return str(value)

def read_rows(bdir, manifest):
    storage = manifest["storage"]; fmt = storage["format"]; path = bdir / storage["path"]
    cols = manifest["columns"]; names = [c["name"] for c in cols]; types = [c["type"] for c in cols]
    if fmt == "parquet":
        import pyarrow.parquet as pq
        t = pq.read_table(path)
        stored_names = list(t.column_names)
        rows = [[conv(r.get(n), ty) for n, ty in zip(names, types)] for r in t.to_pylist()]
    elif fmt == "csv":
        with open(path, newline="", encoding="utf-8") as fh:
            rd = csv.reader(fh); stored_names = next(rd); rows = []
            for rec in rd:
                vals = []
                for cell, ty in zip(rec, types):
                    if cell == "\\N": vals.append(None); continue
                    if cell.startswith("\\"): cell = cell[1:]
                    vals.append(conv(cell, ty))
                rows.append(vals)
    elif fmt == "sqlite":
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = con.execute(f'SELECT * FROM "{storage["table"]}"')
        stored_names = [d[0] for d in cur.description]
        rows = [[conv(v, ty) for v, ty in zip(rec, types)] for rec in cur.fetchall()]
        con.close()
    else:
        raise ValueError(f"unknown format {fmt}")
    return stored_names, rows

def content_hash(columns, rows):
    h = hashlib.sha256()
    h.update(json.dumps(columns, sort_keys=True).encode())
    for row in rows:
        h.update(json.dumps(row, default=str, separators=(",", ":")).encode()); h.update(b"\n")
    return h.hexdigest()

def bundles(root):
    for m in sorted(root.rglob("manifest.json")):
        try: d = json.loads(m.read_text(encoding="utf-8"))
        except Exception: continue
        if isinstance(d, dict) and "contract_version" in d: yield m.parent, d

def check_dir(root):
    root = Path(root); hashes = {}
    for bdir, man in bundles(root):
        rel = bdir.relative_to(root).as_posix(); tag = f"{root.name}/{rel}"
        names = [c["name"] for c in man["columns"]]
        try: stored_names, rows = read_rows(bdir, man)
        except Exception as e:
            out("FAIL", f"C1 {tag}", f"cannot read {man['storage']}: {e!r}"); continue
        out("PASS" if stored_names == names and len(set(names)) == len(names) else "FAIL", f"C1 {tag}", f"format {man['storage']['format']}, columns {stored_names == names}")
        out("PASS" if len(rows) == man["row_count"] else "FAIL", f"C2 {tag}", f"row_count {man['row_count']} stored {len(rows)}")
        nn = [c["name"] for c in man["columns"] if not c.get("nullable", True)]
        nulls = {n: sum(1 for r in rows if r[names.index(n)] is None) for n in nn}
        pk = man.get("primary_key") or []; idx = [names.index(k) for k in pk]
        keys = [tuple(r[i] for i in idx) for r in rows]
        pk_ok = all(None not in k for k in keys) and len(set(keys)) == len(keys)
        out("PASS" if not any(nulls.values()) and pk_ok else "FAIL", f"C3 {tag}", f"nulls in non-nullable { {k: v for k, v in nulls.items() if v} }, pk {pk} unique {pk_ok}")
        h = content_hash(man["columns"], rows); hashes[rel] = (man.get("content_sha256"), h, rows, names)
        out("PASS" if h == man.get("content_sha256") else "FAIL", f"C4 {tag}", f"manifest {str(man.get('content_sha256'))[:16]} recomputed {h[:16]}")
    known = {v[0] for v in hashes.values()}
    refs = {}
    for jf in sorted(root.rglob("*.json")):
        try: d = json.loads(jf.read_text(encoding="utf-8"))
        except Exception: continue
        def walk(o, path):
            if isinstance(o, dict):
                for k, v in o.items(): walk(v, path + "." + k)
            elif isinstance(o, list):
                for i, v in enumerate(o): walk(v, path + f"[{i}]")
            elif isinstance(o, str) and HEX64.match(o):
                if jf.name == "manifest.json" and path == ".content_sha256": return
                refs.setdefault(o, []).append(f"{jf.relative_to(root).as_posix()}{path}")
        walk(d, "")
    unresolved = {h: p for h, p in refs.items() if h not in known}
    out("PASS" if not unresolved else "INFO", f"C5 {root.name}", f"{sum(len(p) for p in refs.values())} hash references in JSON files, {len(refs) - len(unresolved)} distinct resolve to bundles here; unresolved: { {h[:12]: p[:3] for h, p in unresolved.items()} }")
    return hashes

def main(argv):
    if "--formats" in argv:
        i = argv.index("--formats"); dirs, fdirs = argv[:i], argv[i + 1:]
    else:
        dirs, fdirs = argv, []
    for d in dirs: check_dir(d)
    if fdirs:
        per = {d: check_dir(d) for d in fdirs}
        rels = set.intersection(*(set(h) for h in per.values()))
        for rel in sorted(rels):
            items = [(d, per[d][rel]) for d in fdirs]
            same_hash = len({it[1][0] for it in items}) == 1
            same_rows = all(it[1][2] == items[0][1][2] for it in items[1:])
            fmts = [json.loads((Path(d) / rel / "manifest.json").read_text())["storage"]["format"] for d in fdirs]
            out("PASS" if same_hash and same_rows else "FAIL", f"F1 {rel}", f"formats {fmts}: same content_sha256 {same_hash}, equal rows {same_rows}, rows {len(items[0][1][2])}")
    print(f"TOTAL FAIL={fails}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
