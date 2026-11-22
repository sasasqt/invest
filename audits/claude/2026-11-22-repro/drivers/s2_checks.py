"""s2: configuration, CI file and portability checks (stdlib only). Args: <worktree> <out dir> <previous portability json> <bug hunt skill>."""
import ast, json, os, re, subprocess, sys, tomllib
from pathlib import Path
root = Path(sys.argv[1]); out = Path(sys.argv[2]); prev_p = Path(sys.argv[3]); skill = Path(sys.argv[4])
lines = []
def p(s=""): lines.append(s)
r = subprocess.run(["uv", "lock", "--check"], cwd=root, capture_output=True, text=True)
p(f"## uv lock --check: rc={r.returncode}"); p((r.stdout + r.stderr).strip().replace("\n", " | ")[:400])
files = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout.split()
pyps = [f for f in files if f.endswith("pyproject.toml")]
p(); p("## pyproject facts")
reqs = {}
comp_deps = {}
for f in pyps:
    d = tomllib.loads((root / f).read_text(encoding="utf-8"))
    proj = d.get("project", {}); tool = d.get("tool", {})
    reqs[f] = proj.get("requires-python")
    deps = proj.get("dependencies", [])
    comp_deps[f] = deps
    p(f"- {f}: name={proj.get('name')} requires={proj.get('requires-python')} scripts={proj.get('scripts')} ruff_target={tool.get('ruff',{}).get('target-version')} mypy_py={tool.get('mypy',{}).get('python_version')} strict={tool.get('mypy',{}).get('strict')} deps={deps}")
    if f == "pyproject.toml":
        po = tool.get("pytest", {}).get("ini_options", {})
        p(f"  testpaths={po.get('testpaths')} filterwarnings={po.get('filterwarnings')} addopts={po.get('addopts')}")
        inv = tool.get("invest", {})
        p(f"  [tool.invest] keys={list(inv.keys())}")
p(f"- requires-python identical: {len(set(reqs.values()))==1} {set(reqs.values())}")
# console scripts
p(); p("## console scripts")
for f in pyps:
    d = tomllib.loads((root / f).read_text(encoding="utf-8"))
    for name, target in d.get("project", {}).get("scripts", {}).items():
        mod, fn = target.split(":")
        base = (root / f).parent / "src" / Path(*mod.split("."))
        mf = base.with_suffix(".py")
        ok = mf.exists() and re.search(rf"^def {fn}\(", mf.read_text(encoding="utf-8"), re.M) is not None
        p(f"- {name} -> {target}: exists+defined={ok}")
# deps vs imports
p(); p("## declared runtime dependencies vs top-level imports in src/")
stdlib = set(sys.stdlib_module_names)
dist_map = {"invest-data": "invest_data", "invest-mining": "invest_mining", "invest-evaluation": "invest_evaluation"}
for f in pyps:
    if f == "pyproject.toml": continue
    comp = Path(f).parent
    declared = {re.split(r"[<>=!~ \[;]", d)[0].strip().lower() for d in comp_deps[f]}
    decl_mods = {dist_map.get(d, d.replace("-", "_")) for d in declared}
    own = {x.name for x in (root / comp / "src").iterdir() if x.is_dir()}
    top, lazy = set(), set()
    for py in (root / comp / "src").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import): names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: names = [node.module.split(".")[0]]
            for n in names:
                if n in stdlib or n in own or n == "__future__": continue
                # top-level if parent is Module (or try at module level)
                top.add(n)
    undeclared = sorted(top - decl_mods)
    unused = sorted(decl_mods - top)
    p(f"- {comp}: declared={sorted(decl_mods)} imports={sorted(top)} UNDECLARED={undeclared} unused={unused}")
hits = []
for py in (root / "strategy-evaluation").rglob("*.py"):
    t = py.read_text(encoding="utf-8")
    if re.search(r"^\s*(import invest_mining|from invest_mining)", t, re.M): hits.append(str(py.relative_to(root)))
p(f"- invest_mining imported under strategy-evaluation/: {hits or 'none'}")
# coverage floors
p(); p("## coverage floors")
d = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
fl = d.get("tool", {}).get("invest", {}).get("coverage", {}) or d.get("tool", {}).get("invest", {})
p(f"- [tool.invest...] = {json.dumps(fl)[:600]}")
# workflows
p(); p("## .github/workflows")
for wf in sorted((root / ".github/workflows").glob("*.yml")):
    t = wf.read_text(encoding="utf-8")
    p(f"### {wf.name}")
    for m in re.finditer(r"uses:\s*([\w./-]+)@([0-9a-f]+|[\w.]+)\s*(#.*)?", t):
        p(f"- uses {m.group(1)}@{m.group(2)[:12]} full-SHA={bool(re.fullmatch(r'[0-9a-f]{40}', m.group(2)))} comment={(m.group(3) or '').strip()}")
    p(f"- permissions lines: {re.findall(r'^permissions:.*$|^\s+contents:.*$', t, re.M)}; pull_request_target={'pull_request_target' in t}")
    p(f"- python versions: {sorted(set(re.findall(r'3\.1[0-9]', t)))}; timeout-minutes count: {t.count('timeout-minutes')}")
ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
checks_cmds = [l.strip()[len("- run: "):] for l in ci.splitlines() if l.strip().startswith("- run: uv")]
p(); p("## ci.yml checks commands vs docs")
docs = {"README.md": root / "README.md", "PYTHON_GUIDELINES.md": root / "PYTHON_GUIDELINES.md", "CI_CD_GUIDELINES.md": root / "CI_CD_GUIDELINES.md", "bug hunt skill": skill}
for name, path in docs.items():
    try: t = path.read_text(encoding="utf-8")
    except Exception as e: p(f"- {name}: unreadable {e}"); continue
    missing = [c for c in checks_cmds if c not in t and c != "uv sync --frozen" or (c == "uv sync --frozen" and c not in t)]
    p(f"- {name}: missing {missing}")
# shell scripts
p(); p("## shell scripts")
for sh in [f for f in files if f.endswith(".sh")]:
    r = subprocess.run(["bash", "-n", str(root / sh)], capture_output=True, text=True)
    t = (root / sh).read_text(encoding="utf-8")
    p(f"- {sh}: bash -n rc={r.returncode} set -euo pipefail={'set -euo pipefail' in t}")
# portability scan
RULES = {
 "read_write_text_no_encoding": re.compile(r"\.(read_text|write_text)\((?![^)]*encoding=)[^)]*\)"),
 "open_no_encoding": re.compile(r"(?<![\w.])open\((?![^)]*encoding=)(?![^)]*['\"][rwax+]*b[rwax+]*['\"])[^)]*\)"),
 "os_rename": re.compile(r"\bos\.rename\("),
 "path_rename": re.compile(r"\.rename\((?!.*os\.rename)"),
 "python_literal_in_call": re.compile(r"\[\s*['\"]python3?['\"]"),
 "csv_writer_no_lineterminator": re.compile(r"csv\.writer\((?![^)]*lineterminator)"),
 "tmp_literal": re.compile(r"['\"]/tmp\b"),
 "posix_module_import": re.compile(r"^\s*(import|from)\s+(fcntl|pwd|resource|grp|termios)\b", re.M),
}
counts = {}
for f in files:
    if not f.endswith(".py"): continue
    t = (root / f).read_text(encoding="utf-8")
    c = {}
    for k, rx in RULES.items():
        n = len(rx.findall(t))
        if k == "path_rename": n = len([m for m in re.finditer(r"\.rename\(", t) if not t[max(0,m.start()-3):m.start()].endswith("os")])
        c[k] = n
    counts[f] = c
(out / "portability_counts.json").write_text(json.dumps(counts, indent=1, sort_keys=True), encoding="utf-8")
prev = json.loads(prev_p.read_text(encoding="utf-8"))
p(); p("## portability scan")
def tot(sel): 
    s = {}
    for f, c in counts.items():
        if sel(f):
            for k, v in c.items(): s[k] = s.get(k, 0) + v
    return s
p(f"- product (src, tests, scripts) totals: {tot(lambda f: not f.startswith('audits/'))}")
p(f"- audits/gpt/runner totals: {tot(lambda f: f.startswith('audits/'))}")
new, gone = [], []
for f in sorted(set(counts) | set(prev)):
    a = prev.get(f, {}); b = counts.get(f, {})
    for k in RULES:
        if b.get(k, 0) > a.get(k, 0): new.append(f"{f}: {k} {a.get(k,0)} -> {b.get(k,0)}")
        if b.get(k, 0) < a.get(k, 0): gone.append(f"{f}: {k} {a.get(k,0)} -> {b.get(k,0)}")
p(f"- NEW since last run ({len(new)}):"); [p(f"    {x}") for x in new]
p(f"- gone since last run ({len(gone)}):"); [p(f"    {x}") for x in gone]
p("- per-file non-zero (src only):")
for f, c in sorted(counts.items()):
    if "/src/" in f:
        nz = {k: v for k, v in c.items() if v}
        if nz: p(f"    {f}: {nz}")
(out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
