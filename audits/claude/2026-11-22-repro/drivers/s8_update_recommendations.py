"""s8.4: update OUT/recommendations.md for repo audit 2026-11-22 (Route column, evidence, statuses, one new row).
Usage: python update_recommendations.py <recommendations.md> <routes.json>"""
import json, re, sys
path, routes_path = sys.argv[1], sys.argv[2]
routes = json.load(open(routes_path))["recommendations"]
SPLIT = re.compile(r"(?<!\\)\|")
cells_of = lambda line: SPLIT.split(line)[1:-1]
join = lambda c: "|" + "|".join(c) + "|"
D = "2026-11-22 (main eb64ad8)"
EVID = {
 "RA-2026-11-01-6": f" {D}: fix proposed in open PR #73 (head f625d19), unmerged; RA-2026-11-01-2's check still exits 1.",
 "RA-2026-11-01-8": f" {D}: RA-2026-11-01-3 still fails under -W error::Pandas4Warning.",
 "RA-2026-11-01-9": f" {D}: done by 072d66d (#53): report.md marks the censored maximum ('3632 (right-censored: last drawdown not recovered)'); the check exits 0 twice.",
 "RA-2026-11-01-10": f" {D}: 2026-11-01-repro/ra_gzip_tables_carry_wall_clock_mtime.py still exits 1 (the replay at main and the benchmark's real replay carry different wall-clock MTIMEs).",
 "RA-2026-11-01-11": f" {D}: text reads without encoding= rose by 6 net in this week's changed files, all in tests (AST count 97 -> 103, 2026-11-22-repro/encoding_sites_ast.py; test_stats_and_cli.py +5, test_scale_check.py +1).",
 "RA-2026-11-08-4": f" {D}: fix proposed in open PR #66 (head 513470e), unmerged; RA-2026-11-08-1's check still exits 1.",
 "RA-2026-11-08-5": f" {D}: RA-2026-11-08-2's check still exits 1.",
 "RA-2026-11-08-6": f" {D}: +6 net text reads without encoding= in tests this week (see RA-2026-11-01-11).",
 "RA-2026-11-08-7": f" {D}: RA-2026-11-08-3's check still exits 1 on the replay; reporting.py prints no evaluation-window row (only the factor's confirmation window).",
 "RA-2026-11-15-2": f" {D}: wider than entries: zero-volume fills also with delay 1 (2026-11-22-repro/op_zero_volume_fill_delay1.py) and on exits (2026-11-22-repro/op_zero_volume_exit_fill.py), both exit 1 twice; rejecting exits turns them into stuck sales, so coordinate with REVIEW-27 / open PR #64.",
 "RA-2026-11-15-3": f" {D}: no change.",
 "RA-2026-11-15-4": f" {D}: the root-only test ran and passed in this container (uid 0), where the two non-root read-only tests skip; on GitHub (non-root) it is the one that skips, so it still runs in no CI job.",
 "RA-2026-11-15-5": f" {D}: no change (audits/gpt/runner unchanged since 2edd7ae).",
 "RA-2026-11-15-6": f" {D}: no change.",
 "RA-2026-11-15-7": f" {D}: no change.",
}
ACCEPT = {"RA-2026-11-15-2": " `python -I 2026-11-15-repro/ra_fill_on_zero_volume_session.py`, `2026-11-22-repro/op_zero_volume_fill_delay1.py` and `2026-11-22-repro/op_zero_volume_exit_fill.py` (run from the strategy-evaluation venv) all exit 0; the new tests fail on eb64ad8 and pass after the change; REVIEW-27's exit tests still pass "}
STATUS = {"RA-2026-11-01-9": " closed (done by 072d66d, #53) "}
NEW = ["RA-2026-11-22-1",
 "Turn the 2026-11-22 branch check into tests: cover the four decision branches no test reaches (engine order for a name settled between decision and fill, rejected `delisted`; the function-call form of a binary operator with constant arguments and unary plus in the parser; `leg_size`'s k - 1 and `chronological_split`'s k - 1 cut corrections)",
 "P2", "S (one test per branch in strategy-evaluation/tests/test_engine.py or test_strategies, data-mining-framework/tests/test_expressions.py and test_search_and_inference.py)",
 "checks313 coverage on eb64ad8 (work/2026-11-22/tests/checks313/cov.json): engine.py:421-432, expressions.py:272-273 and 291-295, strategies.py:39-40, search.py:121-122 never executed by the suite; 2026-11-22-repro/uncovered_decision_branches.py drives each one and all pass twice (expected values from README.md:59/:81, the infix parser form and a brute force max{k : k / n <= f} over 121,200 pairs; `leg_size`'s k - 1 branch is reached 188 times in that grid); both reviewers: no defect, a test gap",
 "do nothing: the branches behave correctly today, but a regression in any of them (an order on a settled name filling, a constant-only formula slipping into search, a leg one name too large) would pass CI unnoticed; raising the per-file floors alone would not pin these lines",
 "`uv run pytest --cov=invest_mining --cov=invest_evaluation --cov-branch` reports the listed lines as executed, and each new test fails on a copy with its branch removed (for example `leg_size` without the k - 1 return gives a leg one name too large for some (n, fraction) of the brute-force grid)",
 "bug fix routine (coverage mode, tests only)", "open", "2026-11-22", "2026-11-22", "waiting-gpt"]
lines = open(path, encoding="utf-8").read().split("\n")
out = []
for line in lines:
    if line.startswith("| ID | Title |"):
        out.append(line + " Route |"); continue
    if line.startswith("|---|") and out and out[-1].startswith("| ID | Title |"):
        out.append(line + "---|"); continue
    if line.startswith("| RA-"):
        c = cells_of(line); rid = c[0].strip()
        assert len(c) == 11, (rid, len(c))
        if rid in EVID:
            c[4] = c[4].rstrip() + EVID[rid] + " "
            if not c[8].strip().startswith("closed") or rid in STATUS:
                c[10] = " 2026-11-22 "
        if rid in ACCEPT: c[6] = ACCEPT[rid]
        if rid in STATUS: c[8] = STATUS[rid]
        c.append(" " + routes[rid] + " ")
        out.append(join(c)); continue
    out.append(line)
# append the new row after the last RA row
last = max(i for i, l in enumerate(out) if l.startswith("| RA-"))
new_cells = [" " + x.replace("|", "\\|") + " " for x in NEW]
out.insert(last + 1, join(new_cells))
open(path, "w", encoding="utf-8").write("\n".join(out))
for l in out:
    if l.startswith(("| RA-", "| ID")): print(l[:20], len(cells_of(l)), cells_of(l)[-1].strip(), "|", cells_of(l)[8].strip()[:30] if len(cells_of(l)) > 8 else "")
