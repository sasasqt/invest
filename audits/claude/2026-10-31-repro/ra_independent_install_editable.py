"""RA check: the CI independent-install job's install command puts invest-data on the path as an
EDITABLE install of the source tree (uv resolves the component's `[tool.uv.sources] invest-data =
{ workspace = true }`), so the mining and evaluation jobs test invest_data from the checkout, not
from an installed distribution. CI_CD_GUIDELINES.md: "Installs the component into a clean venv with
only its declared dependencies and runs its own tests."

Usage: python3 -I ra_independent_install_editable.py <venv created by `uv venv` +
       `uv pip install --python <venv> <repo>/data-pipeline/data-preparation <repo>/<component> pytest`>
Prints each invest_* distribution's install origin; exits 1 when any is editable
(direct_url.json dir_info.editable == true), which is the defect.
"""
import json, pathlib, sys

venv = pathlib.Path(sys.argv[1])
site = next(venv.glob("lib/python*/site-packages"))
bad = []
for info in sorted(site.glob("invest_*.dist-info")):
    direct = info / "direct_url.json"
    d = json.loads(direct.read_text(encoding="utf-8")) if direct.exists() else {}
    editable = bool(d.get("dir_info", {}).get("editable"))
    print(f"{info.name}: url={d.get('url')} editable={editable}")
    if editable:
        bad.append(info.name)
pth = sorted(p.name for p in site.glob("_editable_impl_*.pth"))
print("editable .pth files:", pth)
print("RESULT:", f"FAIL (editable source-tree installs: {bad})" if bad else "pass (all invest_* installed as distributions)")
sys.exit(1 if bad else 0)
