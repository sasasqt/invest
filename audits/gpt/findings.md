# Maintained findings

Scope: [90b5ca038155b97833b120baa57dfecd05d6f641](https://github.com/sasasqt/invest/commit/90b5ca038155b97833b120baa57dfecd05d6f641),31October2026. One verified **static contract/code contradiction**, one **plausible** benchmark concern; zero locally runtime-confirmed defects. Findings preserve these evidence scopes.

| ID | Consequence / priority | Status and evidence | Action |
|---|---|---|---|
| GA-2026-10-31-1 | Medium / P2 | New, corroborated static contradiction; runtime plausible | [Contract](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/data-mining-framework/src/invest_mining/expressions.py#L290) compared with [unary mask](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/data-mining-framework/src/invest_mining/expressions.py#L337); derive entrant13 vs missing; reproduce twice plus controls after isolation |
| GA-2026-10-31-2 | Medium / P2 | Known/open; confirmed static contract mismatch; local runtime pending | [Settlement application](https://github.com/sasasqt/invest/blob/9913f94b9b795bd9633a6a683e9f420301e400b3/strategy-evaluation/src/invest_evaluation/engine.py#L427) compared with [close-only universe benchmark](https://github.com/sasasqt/invest/blob/9913f94b9b795bd9633a6a683e9f420301e400b3/strategy-evaluation/src/invest_evaluation/engine.py#L568); settlement-inclusive -37.5% versus source 0% |

Known/open: [PR26](https://github.com/sasasqt/invest/pull/26), BH-2026-10-15-1/REVIEW-19 proposes the gross-cost correction; main still contains the old path. INV-COMMON-001/REVIEW-22 remains a known test lead from accessible PR discussions, not newly reproduced here. No main fix was performed or certified.

Full triggering inputs, controls, confidence, fingerprints, locations, acceptance checks, status history and estimates: [findings.json](findings.json). Blind independent review and proposed-drop reasoning: [Verifier A](2026-10-31-repro/verifier-a.md), [comparison](2026-10-31-repro/verifier-a-comparison.md). No substantive disagreement required Verifier B.

## 2026-11-02 continuation

No new runtime-verified product defect. New-to-GPT static confirmation retains the peer's discovery identity.

| ID | Scope and status | Evidence |
|---|---|---|
| GA-2026-11-02-1 / RA-2026-11-01-4 | Medium; confirmed static report/contract omission, runtime unexecuted | reporting.py173â179,248,300; METRICS109; independent verifier |
| GA-2026-11-02-2 / RA-2026-11-01-5 | Low optional summary consistency recommendation | METRICS166â173 versus picks239â276 |

GA-2026-10-31-1 remains open and now has independent static corroboration from RA-2026-11-01-2. GA-2026-10-31-2 is now confirmed at static contract/dataflow scope. A fresh independent reviewer agreed, and the current peer cross-check records a same-SHA runtime failure under alias BH-2026-10-21-2. Local untouched-runtime and verdict-flip acceptance remain pending. All previous entries and histories retained. See findings.json and dated report for current limits.

Delivery reconciliation: existing **INV-PR32-001 P1/high** remains unresolved at runner a73149d3. Safe host-output collection must be verified before new execution. The CSVGZ correction review closure does not certify whole-runner isolation. [Primary maintained review](https://github.com/sasasqt/invest/pull/32#issuecomment-6548582767). No new GA ID/yield for this known root.



## 2026-11-02 Monday data slice

GA-2026-11-02-3: **known K14 / REVIEW-16**, fundamentals reader required-key validation omission independently corroborated on `9913f94b9b795bd9633a6a683e9f420301e400b3`. Static omission confirmed; actual product read/control and financial impact unverified. No newly discovered defect or product execution. [Evidence](2026-11-02-data-rotation/reviewer2/independent-verdict.json).


## 2026-11-03 Tuesday mining slice

GA-2026-10-31-1 / RA-2026-11-01-2 remains **known/open, medium/P2**, independently revalidated on `9913f94b9b795bd9633a6a683e9f420301e400b3`: all four pointwise unary operators lose pre-membership history before a surrounding time-series operation. Search/confirmation/export inherit the evaluator; final eligibility masking is separately correct. Entry/re-entry contract arithmetic gives13/61; premature-mask trace model gives missing. These are not product runtime reproductions.

No new root cause, new optional recommendation or locally runtime-confirmed product defect. Additional future-membership/purge concern dropped at traced scope; runtime fixtures remain queued. [Independent record](2026-11-03-mining/reviewer2/independent-verdict.json). Earlier findings above remain historical at their stated SHAs; today's visit does not revalidate unrelated fields.

## 2026-11-04 evaluation visit

No new defect, runtime-confirmed defect or optional recommendation. GA-2026-11-02-1 / RA-2026-11-01-4 remains a known medium static report omission at `9913f94b9b795bd9633a6a683e9f420301e400b3`. Its censor flag can legitimately describe uncertainty in the eventual maximum even when the earlier longest observed episode recovered. Do not label that recovered episode open. GA-2026-11-02-2 remains optional. [Independent record](2026-11-04-evaluation/reviewer2/independent-verdict.json).


## 5 November 2026 integration visit

No newly discovered verified defect or optional recommendation. Known REVIEW-17/K3 is independently corroborated at static scope: tracked inspection-ledger mutation makes evaluator provenance dirty and recorder refuses. Runtime repetition/control remain pending. [Verification](2026-11-05-integration/reviewer2/independent-verdict.json). C1 ordinary cleanup concern dropped; C2 material recovery concern dropped under the documented gzip recovery contract.


## Engineering update â 6 November 2026

**OPEN-RUNNER-GRAPH-FAILSTOP-001** (alias **INV-PR36-001**) is independently confirmed as a **high / P1 audit-execution blocker** on runner base `cd4d43b48a8c86fc58299aa50cac88b28c508b5e` and PR #36 head `e0181fcbfda9814c53bccec4d0f1d5294487ec2d`. Workspace wheels are built and installed before `installed-graph`; a nonzero graph result is retained but does not stop later format/lint/type/test/CLI/independent-install/synthetic-workflow commands. Two static methods and guarded/vulnerable controls agree; exact-head CI covers only the matching-graph success path. No runtime mismatch or credential exposure is claimed. This is a carried root, so no new GA ID or discovery yield is allocated. [Evidence](2026-11-06-engineering/oracle-results.json) Â· [Independent review](2026-11-06-engineering/reviewer2/independent-verdict.json).

The earlier host-output traversal **INV-PR32-001** remains resolved at reviewed `cd4d43b48a8c86fc58299aa50cac88b28c508b5e`/`e0181fcbfda9814c53bccec4d0f1d5294487ec2d` collection bytes; historical runner `a73149d3` remains blocked. The separate graph fail-stop defect prevents adopting either current runner revision for new product execution.

## 10 November 2026 mining visit

**GA-2026-11-10-1 â medium / P2 â Search and confirm can record hashes from inputs they did not score.** Status: new, independently verified source-level defect at `9913f94b9b795bd9633a6a683e9f420301e400b3`; untouched product runtime unavailable. `_optional_inputs` supplies the universe/fundamentals rows used to build the panel, while `_input_hashes` reopens those paths later for the experiment identity. An AâB alias transition can therefore score A and record B. This can misstate experiment identity, confirmation-use history and downstream evidence binding. A trusted synthetic two-read oracle reproduced the mechanism twice and a stable-A control passed. Fresh Reviewer 2 agreed on the root, medium consequence and correction boundary. Aliases: **BF-2026-11-09-1 / REVIEW-45**; open PR #41 records but does not fix this recording-side root, and PR #38 overlaps the natural fix area.

Required correction: read each optional bundle once and retain manifest/hash with rows for both `search` and fixed-formula `confirm`. Acceptance requires untouched AâB controls twice for universe and fundamentals on both routes, stable A/B controls, and downstream export binding, after runner qualification. [Evidence](2026-11-10-mining/reviewer-comparison.json) Â· [Independent review](2026-11-10-mining/reviewer2/independent-verdict.json).



## 2026-11-11 evaluation update

GA-2026-10-31-2 remains the same root-cause ID and is now **known/open, medium/P2, confirmed static contract mismatch** at 9913f94b9b795bd9633a6a683e9f420301e400b3. Supplied settlements change portfolio holdings, cash and P&L, but the universe equal-weight benchmark ignores them and can feed an optional information-ratio verdict gate. The trusted arithmetic case repeated twice gives settlement-inclusive -37.5% versus current close-only 0%, with no-event/equal-close control 0%. Fresh Reviewer 2 agreed. Same-SHA peer runtime evidence corroborates the wrong event-day benchmark. This run did not execute product code. Acceptance and remaining edge cases are in findings.json and the dated report.
