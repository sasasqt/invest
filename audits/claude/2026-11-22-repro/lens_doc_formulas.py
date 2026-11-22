"""Exploration lens 'CLI defaults and examples against docs': every formula written in a doc,
a script or search's SEED_TEMPLATES, run through parse + check_scale_free on main.
Usage: python -I lens_doc_formulas.py <worktree> <out.tsv>. Prints file:line, verdict, formula."""
import re, subprocess, sys
from pathlib import Path
from invest_mining.expressions import ExpressionError, ScaleError, check_scale_free, features_used, parse
from invest_mining import search
root = Path(sys.argv[1]); out = []
files = [f for f in subprocess.run(["git","-C",str(root),"ls-files"],capture_output=True,text=True).stdout.split()
         if (f.endswith(".md") and not f.startswith(("docs/audits/","runs/"))) or f.endswith(".sh")]
cands = []
for f in files:
    for i, line in enumerate((root/f).read_text(encoding="utf-8").splitlines(), 1):
        for m in re.finditer(r"`([^`]+)`|--expr[= ]+\"([^\"]+)\"|expr=\"([^\"]+)\"", line):
            t = next(g for g in m.groups() if g)
            if re.search(r"[a-z_]+\(|[a-z]\s*[/*+-]\s*[a-z(0-9]", t) and not re.search(r"\.py|uv |--|/[a-z]+/|\.md|=", t):
                cands.append((f"{f}:{i}", t, line))
for t in search.SEED_TEMPLATES:
    cands.append(("search.SEED_TEMPLATES", t, ""))
for where, t, line in cands:
    try:
        node = parse(t)
    except Exception:
        continue
    if not features_used(node): continue
    try:
        check_scale_free(node); v = "accepted"
    except ScaleError as e:
        v = "REFUSED"
    out.append(f"{where}\t{v}\t{t}\t{line.strip()[:200]}")
Path(sys.argv[2]).write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(o.split("\t")[0] + " | " + o.split("\t")[1] + " | " + o.split("\t")[2] for o in out))
