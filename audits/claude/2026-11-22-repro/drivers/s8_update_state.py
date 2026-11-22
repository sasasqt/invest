"""Write OUT/state.json for repo-audit-2026-11-22 (last output of step 8). Usage: python3 -I update_state.py STATE_JSON"""
import json, sys
p = sys.argv[1]; s = json.load(open(p, encoding="utf-8"))
RID, D, SHA = "repo-audit-2026-11-22", "2026-11-22", "eb64ad8f317fdb81d652a0c2ac1bbcbedd4b63f2"
assert s["last_run"] == "2026-11-15"
s["last_sha"], s["last_run"], s["last_run_id"] = SHA, D, RID
s["runs"].append({"run_id": RID, "date": D, "main_sha": SHA, "model": "Fable 5.1 xhigh planned; Opus 5.5 xhigh for the whole run (rule 28 c, Fable gauge 0.96 at 23:37Z)", "report": "audits/claude/2026-11-22.md"})
sp = s["split"]
sp["history"].append({"run_id": RID, "exploitation_pct": 70, "exploration_pct": 30,
    "exploitation": {"lines_read": 1126, "confirmed": 0, "rate_per_1000": 0.0},
    "exploration": {"lines_read": 1472, "confirmed": 0, "rate_per_1000": 0.0},
    "note": "line counts from work/2026-11-22/s8/split_and_share.py; realized 43.3/56.7 by lines; rates equal -> +10 toward exploration (per-run reading, as earlier runs); over the last 4 runs exploitation 0.79 vs exploration 0.32 per 1,000"})
sp["next_exploitation_pct"], sp["next_exploration_pct"] = 60, 40
kept, closed = [], []
for op in s["open_places"]:
    pl = op["place"]
    if "pit.py fundamentals_asof" in pl:
        closed.append({**op, "status": "checked 2026-11-22: 2026-11-22-repro/op_pit_same_available_date.py passes twice (the latest revision wins whatever the row order)"})
    elif "execution.delay >= 1" in pl:
        closed.append({**op, "status": "first half checked 2026-11-22: 2026-11-22-repro/op_zero_volume_fill_delay1.py fails twice (widens RA-2026-11-15-1); the impact half is kept as a new narrowed place"})
    elif "lens_timing_v2.py" in pl:
        closed.append({**op, "status": "fixed 2026-11-22: 2026-11-22-repro/lens_timing_v3.py compares factors/, confirmation.csv and the ledger's dev columns; prefix-invariant on eb64ad8"})
    else:
        kept.append({**op, "status": "unchecked (kept 2026-11-22: RA-2026-11-01-2 fix in open PR #73, unmerged; check still fails on eb64ad8)"})
assert len(kept) == 2 and len(closed) == 3, (len(kept), len(closed))
new = [
 {"source": "run (Opus 5.5 xhigh), narrowed from reviewer 2's 2026-11-15 place", "place": "strategy-evaluation/src/invest_evaluation/engine.py with execution.delay >= 1: impact understated after volume resumes, because volatility collapses on the flat prices of a zero-volume stretch", "status": "unchecked"},
 {"source": "reviewer 2 (Opus 5.5 xhigh), run repo-audit-2026-11-22", "place": "strategy-evaluation/src/invest_evaluation/engine.py:309-310 (exit fallback, min_periods=1): a fill session whose volume is NaN rather than 0 under execution.delay >= 1", "status": "unchecked"},
 {"source": "reviewer 2 (Opus 5.5 xhigh), run repo-audit-2026-11-22", "place": "PR #64 (REVIEW-27 stuck sales): the sizing of stuck sales once zero-volume exits are rejected (RA-2026-11-15-1 fix meets #64)", "status": "unchecked (depends on #64 and the RA-2026-11-15-1 fix)"},
 {"source": "reviewer 2 (Opus 5.5 xhigh), run repo-audit-2026-11-22", "place": "data-mining-framework/src/invest_mining/search.py chronological_split with confirm_start and an embargo at the development/confirmation boundary", "status": "unchecked"},
]
s["open_places"] = kept + new
s["open_places_closed"] += closed + [{"source": "reviewer 2 (Opus 5.5 xhigh), run repo-audit-2026-11-22", "place": "cash interest (financing) in the accounting lens: never exercised (cash_rate 0 in all evaluations)", "status": "checked 2026-11-22: 2026-11-22-repro/cash_rate_check.py with config_cash_rate.json (cash_rate_annual 0.02): 0 of 300 sessions off r/252 on the close-cash basis; accounting identities hold; 29/29 metrics"}]
s["pending_second_review"] = []
s["gpt_cross_check"] = {"gpt_branch_sha": "d3d14ce", "gpt_report_date": "2026-11-15 to 2026-11-21",
    "checked": ["GA-2026-10-31-1", "GA-2026-10-31-2", "GA-2026-11-02-1", "GA-2026-11-10-1", "GA-2026-11-14-1", "GA-2026-11-19-1", "OPEN-RUNNER-GRAPH-FAILSTOP-001"],
    "gpt_verdicts_on_claude": "RA-2026-11-01-1..11 unchanged (9 agree, 2 cannot check); RA-2026-11-08-1 cannot check (2026-11-09, 2026-11-19); RA-2026-11-08-2 cannot check then queued; RA-2026-11-08-3 queued; RA-2026-11-15-1..7 no verdict in 6 GPT reports; 0 disagree"}
s["benchmark_fingerprint"] = "fc1579baf121"
s["benchmark_fingerprint_history"].append({"run_id": RID, "fingerprint": "fc1579baf121", "note": "machine changed from 0fa016b96104 (kernel 6.18.44-fc-v470 -> v726; uv.lock unchanged); not compared; same-host A/B control synth-M +1.9 % (2edd7ae -> eb64ad8); formats series restarts (driver now publishes signals in the case's format); stage timings recorded again"})
s["hunt_rows_added"] = []
s["hunt_rows_added_history"][RID] = []
s["hunt_repro_copies"] = {RID: ["2026-11-22-repro/ra_zero_volume_fill_delay1.py", "2026-11-22-repro/ra_zero_volume_exit_fill.py"]}
s["verifier_b"] = {"launched": False, "reason": "no disagreement with a concrete keep reason: both reviewers agreed on all 6 candidates and 6 measured facts; no GPT disagree on any RA row"}
s["report_written_by"] = "the run itself (Opus 5.5 xhigh), because it never ran on Fable 5.1 (live file MODEL SPLIT)"
s["mirror"] = {"generated": D, "from_run": RID, "files": ["README.md", "findings.md", "recommendations.md", "coverage.md", "gpt.md", "handoffs.md"],
    "copy_on_main": "docs/audits/claude/ on main eb64ad8 equals the 2026-11-08 mirror (f73a1d1); open PR #57 carries the 2026-11-15 mirror; stale since 2026-11-08 (Decisions needed)"}
s["handoff_gate"] = {"first_run": D, "handoffs_made": 0, "routes": {"findings": {"in-pr": 2, "needs-user": 4, "done": 3}, "recommendations": {"in-pr": 2, "todo": 2, "needs-user": 10, "done": 2, "waiting-gpt": 1}}}
s["usage"] = {RID: "Fable gauge 0.96 at 23:37Z (Fable-model event, seven_day 0.53); seven_day 0.07 at 00:01:20Z (Opus event); both reset 2026-11-28T00:00Z; no rate_limit_event in the newest 200 events at 01:10Z; no gauge-log row appended (not in the write list)"}
open(p, "w", encoding="utf-8").write(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
print("state written:", s["last_run_id"], "open_places", len(s["open_places"]), "closed total", len(s["open_places_closed"]))
