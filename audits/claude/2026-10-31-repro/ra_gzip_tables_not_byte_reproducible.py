#!/usr/bin/env python3
"""Check: quantile tables written as .csv.gz are not byte-reproducible (gzip header carries the write time).

Usage: python3 -I ra_gzip_tables_not_byte_reproducible.py <workflow out dir 1> <workflow out dir 2>
Two outputs of the same deterministic workflow (same inputs, same code). For every quantiles/tables/*.csv.gz pair the
decompressed content must be identical (same logical output); the check FAILS (exit 1) when such a pair differs in
bytes, i.e. when the only difference is the gzip header's MTIME field (RFC 1952, bytes 4-7), which breaks byte-level
reproducibility checks and content-addressed caching of the run folder. Expected on fixed code: exit 0 (identical bytes).
"""
import gzip, hashlib, struct, sys
from pathlib import Path
a, b = Path(sys.argv[1]), Path(sys.argv[2]); bad = 0
for pa in sorted(a.glob("quantiles/tables/*.csv.gz")):
    pb = b / pa.relative_to(a)
    ra, rb = pa.read_bytes(), pb.read_bytes(); ca, cb = gzip.decompress(ra), gzip.decompress(rb)
    ma, mb = struct.unpack("<I", ra[4:8])[0], struct.unpack("<I", rb[4:8])[0]
    print(f"{pa.relative_to(a)}: content identical {ca == cb} (sha256 {hashlib.sha256(ca).hexdigest()[:12]}), bytes identical {ra == rb}, gzip MTIME {ma} vs {mb}")
    bad += (ca == cb and ra != rb)
print("FAIL: byte-different copies of identical content" if bad else "PASS: byte-identical"); sys.exit(1 if bad else 0)
