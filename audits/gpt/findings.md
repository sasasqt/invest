# Maintained findings

Scope: [90b5ca038155b97833b120baa57dfecd05d6f641](https://github.com/sasasqt/invest/commit/90b5ca038155b97833b120baa57dfecd05d6f641),31October2026. One verified **static contract/code contradiction**, one **plausible** benchmark concern; zero locally runtime-confirmed defects. Findings preserve these evidence scopes.

| ID | Consequence / priority | Status and evidence | Action |
|---|---|---|---|
| GA-2026-10-31-1 | Medium / P2 | New, corroborated static contradiction; runtime plausible | [Contract](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/data-mining-framework/src/invest_mining/expressions.py#L290) compared with [unary mask](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/data-mining-framework/src/invest_mining/expressions.py#L337); derive entrant13 vs missing; reproduce twice plus controls after isolation |
| GA-2026-10-31-2 | Medium if confirmed / P2 | New, plausible | [Benchmark](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/strategy-evaluation/src/invest_evaluation/engine.py#L539): clarify settlement policy; hand-computed−37.5% compared with static0% |

Known/open: [PR26](https://github.com/sasasqt/invest/pull/26), BH-2026-10-15-1/REVIEW-19 proposes the gross-cost correction; main still contains the old path. INV-COMMON-001/REVIEW-22 remains a known test lead from accessible PR discussions, not newly reproduced here. No main fix was performed or certified.

Full triggering inputs, controls, confidence, fingerprints, locations, acceptance checks, status history and estimates: [findings.json](findings.json). Blind independent review and proposed-drop reasoning: [Verifier A](2026-10-31-repro/verifier-a.md), [comparison](2026-10-31-repro/verifier-a-comparison.md). No substantive disagreement required Verifier B.

## 2026-11-02 continuation

No new runtime-verified product defect. New-to-GPT static confirmation retains the peer's discovery identity.

| ID | Scope and status | Evidence |
|---|---|---|
| GA-2026-11-02-1 / RA-2026-11-01-4 | Medium; confirmed static report/contract omission, runtime unexecuted | reporting.py173–179,248,300; METRICS109; independent verifier |
| GA-2026-11-02-2 / RA-2026-11-01-5 | Low optional summary consistency recommendation | METRICS166–173 versus picks239–276 |

GA-2026-10-31-1 remains open and now has independent static corroboration from RA-2026-11-01-2. GA-2026-10-31-2 remains plausible; peer reports BH-2026-10-21-2 alias, but the original hunt ledger/control is unavailable. All previous entries and histories retained. See findings.json and dated report for current limits.

Delivery reconciliation: existing **INV-PR32-001 P1/high** remains unresolved at runner a73149d3. Safe host-output collection must be verified before new execution. The CSVGZ correction review closure does not certify whole-runner isolation. [Primary maintained review](https://github.com/sasasqt/invest/pull/32#issuecomment-6548582767). No new GA ID/yield for this known root.



## 2026-11-02 Monday data slice

GA-2026-11-02-3: **known K14 / REVIEW-16**, fundamentals reader required-key validation omission independently corroborated on `9913f94b9b795bd9633a6a683e9f420301e400b3`. Static omission confirmed; actual product read/control and financial impact unverified. No newly discovered defect or product execution. [Evidence](2026-11-02-data-rotation/reviewer2/independent-verdict.json).


## 2026-11-03 Tuesday mining slice

GA-2026-10-31-1 / RA-2026-11-01-2 remains **known/open, medium/P2**, independently revalidated on `9913f94b9b795bd9633a6a683e9f420301e400b3`: all four pointwise unary operators lose pre-membership history before a surrounding time-series operation. Search/confirmation/export inherit the evaluator; final eligibility masking is separately correct. Entry/re-entry contract arithmetic gives13/61; premature-mask trace model gives missing. These are not product runtime reproductions.

No new root cause, new optional recommendation or locally runtime-confirmed product defect. Additional future-membership/purge concern dropped at traced scope; runtime fixtures remain queued. [Independent record](2026-11-03-mining/reviewer2/independent-verdict.json). Earlier findings above remain historical at their stated SHAs; today's visit does not revalidate unrelated fields.
