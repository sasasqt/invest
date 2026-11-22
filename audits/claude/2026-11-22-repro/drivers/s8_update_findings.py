"""s8.2: update OUT/findings.md for repo audit 2026-11-22 (Route column, pipe repair, closures, evidence, Last seen).
Usage: python update_findings.py <findings.md> <routes.json>"""
import json, re, sys
path, routes_path = sys.argv[1], sys.argv[2]
routes = json.load(open(routes_path))["findings"]
lines = open(path, encoding="utf-8").read().split("\n")
SPLIT = re.compile(r"(?<!\\)\|")
def cells_of(line):
    return [c for c in SPLIT.split(line)[1:-1]]
def join(cells):
    return "|" + "|".join(cells) + "|"
# pipe repair: merge cell ranges that belong to one column (live file v6 step 8.2)
REPAIR = {"RA-2026-11-01-4": (6, 12), "RA-2026-11-01-5": (8, 10), "RA-2026-11-08-2": (6, 8)}
D = "2026-11-22 (main eb64ad8)"
EVID = {
 "RA-2026-11-01-2": f" {D}: the check exits 1 twice; expressions.py changed in #51 (scale check) but not the unary-mask branch; fix proposed in open PR #73 (head f625d19), unmerged.",
 "RA-2026-11-01-3": f" {D}: still fails under -W error::Pandas4Warning (work/2026-11-22/checks/rerun_ra_2026_11_01_3_pandas4.run1/2.txt); the pip-installed CI-parity jobs print the warnings (wheels 5 lines, data-preparation install 3).",
 "RA-2026-11-08-1": f" {D}: the check exits 1 twice; fix proposed in open PR #66 (head 513470e), unmerged.",
 "RA-2026-11-08-2": f" {D}: the check exits 1 twice.",
 "RA-2026-11-08-3": f" {D}: exits 1 twice on the replay at main (no window row; the only dates are in the benchmark dataset id); on synth-M it passes only because the factor-evidence row 'confirmation window 2021-09-22 to 2022-11-15' equals the evaluation window there (both reviewers); the check greps ISO dates anywhere and needs a labelled window row in its next version.",
 "RA-2026-11-15-1": f" {D}: the check exits 1 twice. Wider than entries (both reviewers, Opus 5.5 xhigh): with execution.delay 1, the default stress scenario delay_1 (config.py:140), 2026-11-22-repro/op_zero_volume_fill_delay1.py fails twice (a 96,660 buy filled at volume 0, participation 0.0193 of trailing ADV); on the exit side 2026-11-22-repro/op_zero_volume_exit_fill.py fails twice (a held name's whole sale, -99,486, filled 5 sessions into a zero-volume stretch). Same root cause: the cap and the gate read the decision session's trailing ADV (engine.py:449-462, :604-605), never the fill session's volume; a patched copy that rejects such fills passes all three checks (reviewer 2). Rejecting exits makes them stuck sales, so the fix meets REVIEW-27 / BF-2026-10-26-1 (open PR #64). The real Yahoo record has 1 zero-volume bar and no such fill under delay 0, 1 or 2. The hunt row's text says entries only; this run does not edit hunt rows.",
}
CLOSE = {"RA-2026-11-01-4": "072d66d (#53, merged 2026-11-18): the check exits 0 twice on the replay at main 2026-11-22 (report.md prints 3632 \\| now '3632 (right-censored: last drawdown not recovered)'); 2026-11-22-repro/censored_rule_check.py agrees with METRICS.md:110 on synth-M, the replay and the rf/MAR run"}
CLOSE["RA-2026-11-01-4"] = CLOSE["RA-2026-11-01-4"].replace(" \\| now", "; now")
out, repaired = [], []
for line in lines:
    if line.startswith("| ID | Kind |"):
        out.append(line + " Route |"); continue
    if line.startswith("|---|") and not out[-1].startswith("|---|") and out and out[-1].startswith("| ID | Kind |"):
        out.append(line + "---|"); continue
    if line.startswith("| RA-"):
        c = cells_of(line)
        rid = c[0].strip()
        if len(c) != 12:
            a, b = REPAIR[rid]
            c = c[:a] + ["\\|".join(c[a:b + 1])] + c[b + 1:]
            repaired.append(rid)
        assert len(c) == 12, (rid, len(c))
        if rid in EVID:
            c[6] = c[6].rstrip() + EVID[rid] + " "
            c[10] = " 2026-11-22 "
        if rid in CLOSE:
            c[4] = " closed "; c[11] = " " + CLOSE[rid] + " "
        c.append(" " + routes[rid] + " ")
        out.append(join(c)); continue
    out.append(line)
open(path, "w", encoding="utf-8").write("\n".join(out))
print("repaired:", repaired)
for line in out:
    if line.startswith(("| RA-", "| ID")):
        print(line[:18], len(cells_of(line)))
