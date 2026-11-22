"""Build validation.csv and the repeat-vs-checks313 per-test comparison (rule 31: deterministic step in code)."""
import csv, json, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

W = Path(sys.argv[1]); SHA = sys.argv[2]
T = W / "tests"
ENV = {
    "checks313": "uv venv, Python 3.13 (uv run), PYTHONHASHSEED unset",
    "checks311": "uv venv at venv311, Python 3.11.x",
    "wheels": "pip venv from built wheels, Python 3.13",
    "indep-data-preparation": "own pip venv, component only",
    "indep-data-mining-framework": "own pip venv, component only",
    "indep-strategy-evaluation": "own pip venv, component without mining (no_mining check)",
    "repeat": "uv venv, Python 3.13, PYTHONHASHSEED=12345",
}
CMD = {
    "sync": "uv sync --frozen", "ruff_format": "ruff format --check .", "ruff_check": "ruff check .",
    "mypy": "mypy (strict, per pyproject)", "pytest": "pytest (CI flags, --cov per ci.yml)",
    "coverage_json": "coverage json", "floors": "coverage floors check (ci.yml)", "md_links": "Markdown link check (ci.yml)",
    "build": "uv build --wheel (3 components)", "venv": "python -m venv", "install": "pip install wheels / component",
    "cli_smoke": "CLI --help smoke (ci.yml)", "no_mining": "import check without data-mining-framework",
}

def junit(p):
    r = ET.parse(p).getroot()
    out = {}
    agg = dict(tests=0, failures=0, errors=0, skipped=0, time=0.0)
    for ts in r.iter("testsuite"):
        for k in ("tests", "failures", "errors", "skipped"):
            agg[k] += int(ts.get(k, 0))
        agg["time"] += float(ts.get("time", 0))
        for tc in ts.iter("testcase"):
            key = tc.get("classname", "") + "::" + tc.get("name", "")
            st = "passed"
            for child in tc:
                if child.tag in ("failure", "error"): st = "failed"
                elif child.tag == "skipped":
                    st = "xfailed" if "xfail" in (child.get("type", "") + child.get("message", "")).lower() else "skipped"
            out[key] = st
    return agg, out

def warnings(p):
    if not p.exists(): return ""
    txt = p.read_text(errors="replace")
    m = re.findall(r"(\d+) warnings?", txt.splitlines()[-1] if txt.splitlines() else "")
    tail = "\n".join(txt.splitlines()[-3:])
    m = re.findall(r"(\d+) warnings?", tail)
    return m[-1] if m else "0"

rows = []
for job in ["checks313", "checks311", "wheels", "indep-data-preparation", "indep-data-mining-framework", "indep-strategy-evaluation", "repeat"]:
    d = T / job
    steps = []
    if (d / "steps.csv").exists():
        steps = [r for r in csv.reader((d / "steps.csv").open()) if r]
    elif job == "repeat":
        steps = [["pytest", "?", ""]]
    for name, rc, secs in steps:
        row = dict(command=CMD.get(name, name) + (" with PYTHONHASHSEED=12345" if job == "repeat" else ""), job=job,
                   environment=ENV[job], revision=SHA, outcome="", collected="", passed="", failed="", skipped="",
                   xfailed="", warnings="", duration_s=secs, exit_code=rc, evidence=str(d / (name + ".log")))
        if name == "pytest" and (d / "junit.xml").exists():
            agg, cases = junit(d / "junit.xml")
            st = list(cases.values())
            row.update(collected=len(st), passed=st.count("passed"), failed=st.count("failed"),
                       skipped=st.count("skipped"), xfailed=st.count("xfailed"),
                       warnings=warnings(d / "pytest.log"), evidence=str(d / "junit.xml"))
            if job == "repeat" and not row["duration_s"]:
                row["duration_s"] = round(agg["time"], 1)
                row["exit_code"] = "0" if agg["failures"] + agg["errors"] == 0 else "1"
        row["outcome"] = "pass" if str(row["exit_code"]) == "0" else ("fail" if row["exit_code"] not in ("?", "") else "unknown")
        rows.append(row)

with (W / "validation.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

# per-test comparison repeat vs checks313
cmp = {}
if (T / "repeat" / "junit.xml").exists():
    _, a = junit(T / "checks313" / "junit.xml"); _, b = junit(T / "repeat" / "junit.xml")
    diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    cmp = dict(checks313=len(a), repeat=len(b), differing=[(k, a.get(k), b.get(k)) for k in diff])
    skipped = sorted(k for k, v in a.items() if v != "passed")
    cmp["not_passed_in_checks313"] = skipped
(W / "tests" / "repeat_vs_checks313.json").write_text(json.dumps(cmp, indent=1))
for r in rows:
    print(r["job"], r["command"][:40], r["outcome"], r["collected"], r["passed"], r["failed"], r["skipped"], r["warnings"], r["duration_s"])
print(json.dumps({k: (v if k != "differing" else v[:20]) for k, v in cmp.items()}, indent=1)[:3000])
