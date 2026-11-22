"""Rule 31 helper for the 2026-11-22 report: (1) lines read per side of the explore/exploit split and the
4-run rates; (2) the 28-day reviewed-or-partial share by Claude and by either model.
Usage: python3 -I split_and_share.py MAIN_WORKTREE STATE_JSON COVERAGE_MAP_JSON GPT_COVERAGE_CSV LS_FILES W
Definitions (stated in the report):
  exploration = whole files of this run's rotation slice (coverage map slices[2026-11-22]) + the random draw;
  exploitation = added lines since last_sha (git diff --numstat) in the deep-read files + whole test files
  changed since last_sha that are outside the slice and were read for test quality."""
import csv, datetime as dt, json, subprocess, sys
from pathlib import Path
main, state_p, cmap_p, gcsv_p, ls_p, W = sys.argv[1:7]
W = Path(W); DATE = "2026-11-22"; LAST = "2edd7ae"; HEAD = "eb64ad8"
def lines(p): return int(subprocess.run(["git", "-C", main, "show", f"{HEAD}:{p}"], capture_output=True, check=True).stdout.count(b"\n"))
def added(p):
    out = subprocess.run(["git", "-C", main, "diff", "--numstat", LAST, HEAD, "--", p], capture_output=True, text=True, check=True).stdout.split()
    return int(out[0]) if out and out[0].isdigit() else 0
cmap = json.load(open(cmap_p, encoding="utf-8"))
slice_files = cmap["slices"][DATE]
draw = ["audits/gpt/runner/verify_installed.py"]
deep = [l.strip() for f in ("deep-read.reviewed.txt", "deep-read.partially_reviewed.txt") for l in open(W / "s8/credit" / f) if l.strip()]
tq = [l.strip() for f in ("test-quality.reviewed.txt", "test-quality.partially_reviewed.txt") for l in open(W / "s8/credit" / f) if l.strip()]
changed = set(subprocess.run(["git", "-C", main, "diff", "--name-only", LAST, HEAD], capture_output=True, text=True, check=True).stdout.split())
explore = {p: lines(p) for p in slice_files + [d for d in draw if d not in slice_files]}
exploit_diff = {p: added(p) for p in deep if p not in explore}
exploit_tests = {p: lines(p) for p in tq if p not in slice_files and p in changed}
ex_lines = sum(explore.values()); ep_lines = sum(exploit_diff.values()) + sum(exploit_tests.values())
print(f"exploration lines {ex_lines}: " + ", ".join(f"{p} {n}" for p, n in explore.items()))
print(f"exploitation lines {ep_lines}: diff " + ", ".join(f"{p} +{n}" for p, n in exploit_diff.items() if n) + "; tests " + ", ".join(f"{p} {n}" for p, n in exploit_tests.items()))
tot = ex_lines + ep_lines
print(f"realized split by lines: exploitation {100*ep_lines/tot:.1f} %, exploration {100*ex_lines/tot:.1f} %")
st = json.load(open(state_p, encoding="utf-8"))
hist = st["split"]["history"][-3:] + [{"run_id": f"repo-audit-{DATE}", "exploitation": {"lines_read": ep_lines, "confirmed": 0}, "exploration": {"lines_read": ex_lines, "confirmed": 0}}]
for side in ("exploitation", "exploration"):
    L = sum(h[side]["lines_read"] for h in hist); C = sum(h[side]["confirmed"] for h in hist)
    print(f"4-run {side}: {C} confirmed / {L} lines = {1000*C/L:.2f} per 1,000")
er = 0.0; xr = 0.0
print(f"this run: exploitation {er:.2f}, exploration {xr:.2f} per 1,000 -> exploration >= exploitation -> next split +10 toward exploration: 60/40 (from 70/30)")
# share
tracked = [l.strip() for l in open(ls_p) if l.strip()]
run = dt.date.fromisoformat(DATE); cut = run - dt.timedelta(days=28)
REV = {"reviewed", "partially_reviewed"}
claude = {p for p in tracked if any(h["status"] in REV and dt.date.fromisoformat(h["date"]) >= cut for h in cmap["files"].get(p, {}).get("history", []))}
g = {r["path"]: r for r in csv.DictReader(open(gcsv_p, encoding="utf-8"))}
gpt = {p for p in tracked if g.get(p, {}).get("status") in REV | {"verified"} and g[p].get("last_review_date") and dt.date.fromisoformat(g[p]["last_review_date"][:10]) >= cut}
newest = max((r.get("last_review_date") or "") for r in g.values())
print(f"tracked {len(tracked)}; claude 28-day {len(claude)} ({100*len(claude)/len(tracked):.1f} %); gpt 28-day {len(gpt)}; either {len(claude|gpt)} ({100*len(claude|gpt)/len(tracked):.1f} %); gpt file newest review date {newest}")
print("not reviewed by either in 28 days:", sorted(set(tracked) - claude - gpt))
