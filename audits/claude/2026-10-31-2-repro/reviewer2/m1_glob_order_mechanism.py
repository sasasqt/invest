"""M1: is test_factor_from_another_experiment_is_refused dependent on directory iteration order?
Replays the test's setup (synthetic 25 x 260, two searches with seeds 0 and 5, top-k 2) in a temp dir and
runs the export for EVERY factor file in first/factors. The test passes only if the file next(glob) returns
is refused with 'was selected in experiment'. Exit 1 if the two files give different messages."""
import re, sys, tempfile
from pathlib import Path
from invest_data.cli import main as data_main
from invest_mining.cli import main

tmp = Path(tempfile.mkdtemp())
data = tmp / "data"
assert data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"]) == 0
book = tmp / "ledger.jsonl"
for out, seed in (("first", 0), ("other", 5)):
    assert main(["search", "--data", str(data), "--trials", "10", "--top-k", "2", "--out", str(tmp / out), "--seed", str(seed), "--ledger", str(book)]) == 0
files = sorted((tmp / "first" / "factors").glob("*.json"))
print("factor files in first/factors:", [f.name for f in files], "| next(glob) here ->", next((tmp / "first" / "factors").glob("*.json")).name)
msgs = {}
for i, f in enumerate(files):
    try:
        rc = main(["export", "--data", str(data), "--factor", str(f), "--confirmation", str(tmp / "other"), "--out", str(tmp / f"x{i}")])
        msgs[f.name] = f"rc={rc} (no SystemExit)"
    except SystemExit as e:
        msgs[f.name] = str(e)
for k, v in msgs.items():
    print(f"{k}: {v!r} -> test regex 'was selected in experiment' matches: {bool(re.search('was selected in experiment', v))}")
kinds = {bool(re.search('was selected in experiment', v)) for v in msgs.values()}
sys.exit(1 if len(kinds) > 1 else 0)
