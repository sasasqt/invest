"""Check: the gzip members of quantiles/tables/*.csv.gz carry the wall-clock time of the run in their header
(RFC 1952 MTIME field), so two runs with identical content produce byte-different artifacts even though every
content hash matches. Reproducible artifacts need MTIME = 0 (or a fixed value). Related: TODO BUILD-03 asks for
reproducible text artifacts (newline="\\n").
Usage: python ra_gzip_tables_carry_wall_clock_mtime.py <quantiles dir> [<second quantiles dir>]
Exit 0 when every member's MTIME is 0, 1 when a wall-clock MTIME is present (and, with two dirs, differs between runs), 2 on setup error."""
import glob, os, struct, sys
dirs = sys.argv[1:]
if not dirs: print("usage"); sys.exit(2)
bad = []; seen = {}
for d in dirs:
    files = sorted(glob.glob(os.path.join(d, "tables", "*.csv.gz")))
    if not files: print(f"setup error: no tables/*.csv.gz under {d}"); sys.exit(2)
    for f in files:
        with open(f, "rb") as fh: head = fh.read(10)
        if head[:2] != b"\x1f\x8b": print(f"setup error: {f} is not gzip"); sys.exit(2)
        mtime = struct.unpack("<I", head[4:8])[0]
        print(f"{f}: MTIME={mtime}")
        seen.setdefault(os.path.basename(f), set()).add(mtime)
        if mtime != 0: bad.append(f)
if bad:
    differ = [k for k, v in seen.items() if len(v) > 1]
    print(f"FAIL: {len(bad)} gzip member(s) carry a wall-clock MTIME" + (f"; {differ} differ between the two runs (byte-different artifacts for identical content)" if differ else ""))
    sys.exit(1)
print("PASS: all MTIME fields are 0"); sys.exit(0)
