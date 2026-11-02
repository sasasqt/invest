# Independent Reviewer 2 — static-only

Pinned main: `90b5ca038155b97833b120baa57dfecd05d6f641`. No repository imports, tests, builds, or downloaded scripts executed. No real observations or runs/ledgers data accessed. Model and effort are not exposed.

| Candidate | Decision | Severity | Evidence conclusion |
|---|---|---|---|
| AUDIT-RUNNER-CSVGZ-001 | Drop original omission as corrected in v2; runtime acceptance pending | Prior audit evidence gap medium | Static branches include decompressed CSV, ordered JSONL and other files. Gate proves normalized repeatability only. |
| RA1 | Keep existing duplicate CI item | High operational by peer scale; test defect low | Fresh CI metadata red, wrong guard possible statically; runtime causal details attributed. |
| RA2 | Keep, duplicate GA1 | Medium | Confirmed static full-history contradiction; version/migration missing in proposed correction. |
| RA3 | Keep compatibility risk, soften future certainty | Low | Plausible; static source does not independently prove pandas3.1/4 behavior. |
| RA4 | Keep | Medium | Confirmed static censor-metadata loss; saved-run numbers not checked. |
| RA5 | Keep report/doc recommendation | Low | Confirmed static omitted-default-summary fields, soft requirement. |

Recommendation RA6 needs an operator-version decision. RA8 must preserve exact percentile round trips. RA9 must resolve longest-completed versus current-open censor metadata before printing N+. RA10 remains hygiene, not a product defect; RA11 remains duplicate BUILD-03. Current open PR31 already addresses RA1; PR32 contains runner correction.

Not all correctness questions are answered. Checked branches/callers, sibling glob tests, drawdown metadata/rendering and summary contract, plus semantic gate/reference logic. Highest remaining places: membership-gap label economics; benchmark settlement/no-bar/reentry economics; same-blob isolated semantic-gate negative controls and expected output inventory. Details, missing evidence and drop counterfactuals are in independent-verdict.json; exact source ranges are in read-ranges.json.
