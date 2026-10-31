# Maintained findings

Scope: [90b5ca038155b97833b120baa57dfecd05d6f641](https://github.com/sasasqt/invest/commit/90b5ca038155b97833b120baa57dfecd05d6f641),31October2026. One verified **static contract/code contradiction**, one **plausible** benchmark concern; zero locally runtime-confirmed defects. Findings preserve these evidence scopes.

| ID | Consequence / priority | Status and evidence | Action |
|---|---|---|---|
| GA-2026-10-31-1 | Medium / P2 | New, corroborated static contradiction; runtime plausible | [Contract](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/data-mining-framework/src/invest_mining/expressions.py#L290) compared with [unary mask](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/data-mining-framework/src/invest_mining/expressions.py#L337); derive entrant13 vs missing; reproduce twice plus controls after isolation |
| GA-2026-10-31-2 | Medium if confirmed / P2 | New, plausible | [Benchmark](https://github.com/sasasqt/invest/blob/90b5ca038155b97833b120baa57dfecd05d6f641/strategy-evaluation/src/invest_evaluation/engine.py#L539): clarify settlement policy; hand-computed−37.5% compared with static0% |

Known/open: [PR26](https://github.com/sasasqt/invest/pull/26), BH-2026-10-15-1/REVIEW-19 proposes the gross-cost correction; main still contains the old path. INV-COMMON-001/REVIEW-22 remains a known test lead from accessible PR discussions, not newly reproduced here. No main fix was performed or certified.

Full triggering inputs, controls, confidence, fingerprints, locations, acceptance checks, status history and estimates: [findings.json](findings.json). Blind independent review and proposed-drop reasoning: [Verifier A](2026-10-31-repro/verifier-a.md), [comparison](2026-10-31-repro/verifier-a-comparison.md). No substantive disagreement required Verifier B.
