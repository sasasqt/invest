"""Regenerate OUT/mirror/ from the ledgers, the coverage map and GPT's findings (live file v6, Paths: mirror).

Usage: python3 -I gen_mirror.py OUT FACTS_JSON GPT_FINDINGS_MD PARENT_COMMIT
Counts are computed here from the ledgers (rule 31); prose comes from FACTS_JSON.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

OUT, FACTS, GPTF, PARENT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
f = json.loads(FACTS.read_text(encoding="utf-8"))
SPLIT = re.compile(r"(?<!\\)\|")

def table(path):
    hdr, rows = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ID ") or line.startswith("| Handoff ID "):
            hdr = [c.strip() for c in SPLIT.split(line)[1:-1]]
        elif line.startswith("| RA-") or line.startswith("| HO-"):
            cells = [c.strip() for c in SPLIT.split(line)[1:-1]]
            assert len(cells) == len(hdr), (path, cells[0], len(cells), len(hdr))
            rows.append(dict(zip(hdr, cells)))
    return hdr, rows

def row(cells):
    return "| " + " | ".join(cells) + " |"

fh, frows = table(OUT / "findings.md")
rh, rrows = table(OUT / "recommendations.md")
hh, hrows = table(OUT / "handoffs.md")
open_f = [r for r in frows if r["Status"] in ("open", "plausible") or r["Status"].startswith("fix proposed in PR #")]
open_r = [r for r in rrows if r["Status"] == "open"]
open_h = [r for r in hrows if r["Status"] in ("open", "in progress")]
tag = f"run `{f['run_id']}`, main `{f['main_short']}`"
m = OUT / "mirror"

# findings.md
lines = [f"# Repo audit findings (Claude) — open and plausible rows, generated {f['date']}", "",
         f"Generated read-only mirror of `audits/claude/findings.md` on branch `claude/repo-audits` ({tag}). Closed rows stay in the ledger on the branch. Do not edit here.", "",
         row(fh), row(["---"] * len(fh))] + [row([r[h] for h in fh]) for r in open_f]
(m / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# recommendations.md
cols = ["ID", "Priority", "Title", "Acceptance criteria", "Owner", "Route"]
lines = [f"# Repo audit recommendations (Claude) — open rows, generated {f['date']}", "",
         f"Generated read-only mirror of `audits/claude/recommendations.md` ({tag}). Do not edit here.", "",
         row(cols), row(["---"] * len(cols))] + [row([r[c] for c in cols]) for r in open_r]
(m / "recommendations.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# handoffs.md
lines = [f"# Repo audit handoffs (Claude) — open and in-progress rows, generated {f['date']}", "",
         f"Generated read-only mirror of `audits/claude/handoffs.md` ({tag}). Done and dropped rows stay in the ledger on the branch. Do not edit here.", "",
         row(hh), row(["---"] * len(hh))] + [row([r[h] for h in hh]) for r in open_h]
if not open_h:
    lines += ["", "No open handoffs: no row has met every condition of the handoff gate yet (see the ledger's dated notes)."]
(m / "handoffs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# coverage.md
cov = (OUT / "coverage-map.md").read_text(encoding="utf-8")
(m / "coverage.md").write_text(f"<!-- generated read-only mirror of audits/claude/coverage-map.md, run {f['run_id']} -->\n" + cov, encoding="utf-8")

# gpt.md: GPT's open items at the cross-check commit, with this side's newest verdict
verdicts = {}
for line in (OUT / "cross-check.md").read_text(encoding="utf-8").splitlines():
    if line.startswith("| GA-") or line.startswith("| OPEN-"):
        c = [x.strip() for x in SPLIT.split(line)[1:-1]]
        verdicts[c[0]] = (c[1], c[4])          # the newest row wins (rows are appended)
gpt_text = GPTF.read_text(encoding="utf-8")
closed_words = ("closed on main", "fixed on main")
gl = [f"# GPT audit findings with Claude's verdicts, generated {f['date']}", "",
      f"GPT items read from `audits/gpt/findings.md` on branch `gpt/repo-audits` at `{f['gpt_commit']}`; verdicts from `audits/claude/cross-check.md`. Items Claude found closed or fixed on main drop out. Do not edit here.", "",
      "| GPT ID | Where GPT records it | Claude verdict (date) |", "|---|---|---|"]
kept = 0
for gid, (verdict, date) in sorted(verdicts.items()):
    if any(w in verdict for w in closed_words):
        continue
    if gid not in gpt_text:
        continue
    where = "table row" if re.search(r"^\| " + re.escape(gid), gpt_text, re.M) else "prose section"
    gl.append(row([gid, where, f"{verdict} ({date})"])); kept += 1
(m / "gpt.md").write_text("\n".join(gl) + "\n", encoding="utf-8")

# README.md
sev = Counter(r["Severity"] for r in open_f)
st = Counter(r["Status"] for r in frows)
routes_f = Counter(r["Route"].split(":")[0] for r in frows)
routes_r = Counter(r["Route"].split(":")[0] for r in rrows)
v = Counter()
for gid, (verdict, date) in verdicts.items():
    if date == f["date"]:
        v[verdict.split()[0].rstrip(";,")] += 1   # first word: agree / disagree / cannot
fmt = lambda c: ", ".join(f"{k} {n}" for k, n in sorted(c.items()))
R = [f"# Claude repo audit — mirror on main", "",
     f"Generated by run `{f['run_id']}` ({f['date']}) on branch `claude/repo-audits` (parent commit `{PARENT}`), auditing main `{f['main_full']}`. Every file in this folder is a generated read-only copy; the ledgers live on the branch and the audit never writes main. Latest report: [audits/claude/{f['date']}.md](https://github.com/sasasqt/invest/blob/claude/repo-audits/audits/claude/{f['date']}.md).", "",
     "## Health and limits", ""] + [f"- {h}" for h in f["health"]] + ["",
     "## Counts", "",
     f"- Findings ledger: {st.get('open',0)} open, {st.get('plausible',0)} plausible, {sum(n for k,n in st.items() if k.startswith('fix proposed'))} fix proposed, {st.get('closed',0)} closed; open or plausible by severity: {fmt(sev)}.",
     f"- Recommendations ledger: {len(open_r)} open of {len(rrows)}.",
     f"- Routes (handoff gate): findings {fmt(routes_f)}; recommendations {fmt(routes_r)}. Open handoffs: {len(open_h)}.",
     f"- GPT cross-check this run (GPT at `{f['gpt_commit']}`): {sum(v.values())} GPT items checked: {fmt(v)}; {kept} GPT items still open are listed in `gpt.md`.",
     "", "## This run's candidate lines for TODO.md", ""] + (f["todo_candidates"] or ["- none"]) + [f"- Note: {n}" for n in f["todo_notes"]] + ["",
     "## This run's candidate lines for ROADMAP.md", ""] + ([f"- {x}" for x in f["roadmap_candidates"]] or ["- none"]) + ["",
     "## Files", "",
     "- `findings.md`: open and plausible findings (full ledger columns).",
     "- `recommendations.md`: open recommendations (ID, priority, title, acceptance criteria, owner, route).",
     "- `coverage.md`: the latest review coverage map.",
     "- `gpt.md`: the GPT audit's open findings at the commit the cross-check read, with Claude's verdicts.",
     "- `handoffs.md`: open and in-progress handoffs of the handoff gate.",
     "", "Regenerated every run; a copy on main as `docs/audits/claude/` needs no edit. Staleness: compare the run id above with the newest report on the branch."]
assert len(R) <= 120, len(R)
(m / "README.md").write_text("\n".join(R) + "\n", encoding="utf-8")
print(f"mirror: findings {len(open_f)}, recommendations {len(open_r)}, handoffs {len(open_h)}, gpt {kept}, README {len(R)} lines; verdicts {dict(v)}")
