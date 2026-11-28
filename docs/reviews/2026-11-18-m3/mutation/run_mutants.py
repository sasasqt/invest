"""Apply each mutant to the repo COPY, run its target tests, then the wider set if it survives."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mutants import MUTANTS

R = Path(__file__).resolve().parent.parent
REPO = Path(os.environ["MUTATION_REPO"])  # a throwaway copy of the checkout at eb64ad8
PY = os.environ["INVEST"] + "/.venv/bin/python"
env = dict(os.environ)
env["PYTHONDONTWRITEBYTECODE"] = "1"
env["PYTHONPATH"] = ":".join(
    str(REPO / p)
    for p in (
        "data-pipeline/data-preparation/src",
        "data-mining-framework/src",
        "strategy-evaluation/src",
    )
)
env["PATH"] = os.environ["INVEST"] + "/.venv/bin:" + env["PATH"]
only = set(sys.argv[1:])
results = []


def run(tests):
    t = time.time()
    p = subprocess.run(
        [PY, "-m", "pytest", "-p", "no:cacheprovider", "-x", "-q", *tests],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )
    return p.returncode, round(time.time() - t, 1), p.stdout[-1500:]


for mid, rel, old, new, target, wider in MUTANTS:
    if only and mid not in only:
        continue
    f = REPO / rel
    src = f.read_text(encoding="utf-8")
    assert src.count(old) == 1, (mid, src.count(old))
    f.write_text(src.replace(old, new), encoding="utf-8")
    try:
        rc, dt, out = run(target)
        rec = {
            "id": mid,
            "file": rel,
            "target": target,
            "target_rc": rc,
            "target_s": dt,
            "target_tail": out.strip().splitlines()[-3:],
        }
        if rc == 1:
            rec["verdict"] = "killed by target"
        elif rc == 0:
            rc2, dt2, out2 = run(wider)
            rec.update(
                {
                    "wider": wider,
                    "wider_rc": rc2,
                    "wider_s": dt2,
                    "wider_tail": out2.strip().splitlines()[-6:],
                }
            )
            rec["verdict"] = (
                "SURVIVED target; killed by wider set"
                if rc2 == 1
                else ("SURVIVED target and wider set" if rc2 == 0 else f"wider rc {rc2}")
            )
        else:
            rec["verdict"] = f"target error rc {rc}"
    finally:
        f.write_text(src, encoding="utf-8")
    print(json.dumps(rec), flush=True)
    results.append(rec)
out = Path(os.environ.get("MUTATION_OUT", ".")) / (
    "results_" + ("_".join(sorted(only)) if only else "all") + ".json"
)
out.write_text(json.dumps(results, indent=1))
