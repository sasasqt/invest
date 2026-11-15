"""Cross-check of GPT row GA-2026-11-14-1 (stdlib only): does the runner's csv.gz branch
(audits/gpt/runner/runner_workload.py:107-113 at main 2edd7ae: gzip.open(path, 'rb').read(),
catching OSError/EOFError/zlib.error as 'Invalid compressed CSV') accept a zero-byte .csv.gz?
Expected by the branch's own message: a file that is not valid gzip is refused.
usage: python -I ga_2026_11_14_1_zero_byte_gzip.py <tmp dir>"""
import gzip, sys, zlib
from pathlib import Path
tmp = Path(sys.argv[1]); tmp.mkdir(parents=True, exist_ok=True)
cases = {"zero_bytes.csv.gz": b"", "truncated.csv.gz": gzip.compress(b"a,b\n1,2\n")[:10], "not_gzip.csv.gz": b"a,b\n1,2\n"}
accepted = []
for name, data in cases.items():
    p = tmp / name; p.write_bytes(data)
    try:
        with gzip.open(p, "rb") as stream:
            payload = stream.read()
        print(f"{name}: ACCEPTED, payload {payload!r}"); accepted.append(name)
    except (OSError, EOFError, zlib.error) as exc:
        print(f"{name}: refused ({type(exc).__name__}: {exc})")
bad = [n for n in accepted]
print("RESULT:", "zero-byte file accepted as empty CSV content (GA-2026-11-14-1 reproduced at stdlib scope)" if "zero_bytes.csv.gz" in bad else "all refused")
sys.exit(1 if "zero_bytes.csv.gz" in bad else 0)
