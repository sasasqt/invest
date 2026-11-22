"""Fill the report draft's placeholders from report_tables.md and apply the listed text fixes (rule 31).
Usage: python3 -I fill_report.py DRAFT TABLES OUT_REPORT"""
import re, sys
draft, tables, out = (open(p, encoding="utf-8").read() if i < 2 else p for i, p in enumerate(sys.argv[1:4]))
for key in ("TESTMATRIX", "BENCH", "RECS", "OVERLAP"):
    m = re.search(rf"<!-- {key} -->\n(.*?)\n<!-- /{key} -->", tables, re.S)
    assert m and draft.count("{{" + key + "}}") == 1, key
    draft = draft.replace("{{" + key + "}}", m.group(1))
fixes = [
 ("{{REPORT_LINK_0101}}", "https://github.com/sasasqt/invest/blob/4930f9ee9ecf65735822456392d2253fdc93bd9e/audits/claude/2026-11-01.md"),
 ("both workflow scripts pass `bash -n`", "both shell scripts in scripts/ pass `bash -n`"),
 ("- Fold proposal (restated from 2026-11-08, unchanged by this run's numbers): keep in the repo audit the CI parity jobs, flaky detection, the saved-record replay with drift attribution, benchmarks with the same-host control, the coverage map, the cross-model check and the recommendations ledger; fold the random-draw exploration read and the per-run lens families into the bug hunt only after four runs, since these checks found nothing anywhere so far. The owner thread proposes any change.",
  "- Fold proposal (made by the 2026-11-08 run, restated unchanged by this run's numbers): keep in the repo audit CI parity, flaky detection, the saved-record replay with drift attribution, benchmarks (this week's same-host control again showed why), the coverage map, the cross-model check and the recommendations ledger; fold into the bug hunt the random-draw exploration read and the per-run re-runs of earlier checks (the hunt re-runs its repro folder nightly); fold into the docs audit the doc-numbers-vs-replay table. The decision stays with you (no answer recorded yet); the owner thread proposes any change."),
]
for old, new in fixes:
    assert draft.count(old) == 1, old[:60]
    draft = draft.replace(old, new)
assert "{{" not in draft
open(out, "w", encoding="utf-8").write(draft)
print("report lines", draft.count("\n"))
