# R1 / Verifier A comparison

Pinned main: `90b5ca038155b97833b120baa57dfecd05d6f641`.

Comparison occurred only after `independent-verdicts.md` was saved. Then read `reviewer1-initial.json`; no old reviewer notes were consulted.

| Candidate | R1 initial | Verifier A independent | Comparison / final evidence label |
|---|---|---|---|
| C1 / GA-2026-10-31-1 | Keep, medium/P2; static contract/code contradiction, runtime plausible | Keep, medium/P2; independently derived positive-close abs/ts_sum example | Agree. Textual/implementation contradiction corroborated; runtime consequence remains plausible. No executed reproduction or control. Do not count as confirmed-runtime discovery yield. |
| C2 / GA-2026-10-31-2 | Keep, medium/P2; plausible benchmark settlement defect | Keep, medium/P2; independent nonzero-settlement wealth calculation, policy caveat | Agree. Input omission statically certain; settlement-inclusive benchmark interpretation and runtime result remain plausible. No verdict-flip claim. |
| C3 | Drop as new discovery; preserve known/open PR26 / BH-2026-10-15-1 | Same conditional duplicate drop; no-cost rerun equality is not a general invariant | Agree. Main reviewer reports GitHub primary PR body verification and will pin exact PR head. This helper has not independently fetched that remote evidence. Keep known/open at audited main; no new GA allocation. |

No substantive keep/drop, severity, or interpretation disagreement remains on this evidence version. Verifier B is not warranted. Consensus adds no runtime evidence and does not resolve missing isolation or benchmark-policy clarity.

Review-stage elapsed time: unavailable (no reliable start/end monotonic timing captured). Model/effort unavailable. No new source reading beyond the previously recorded ranges was performed for this comparison. Actual repository executions: zero.

The per-candidate missing evidence, checked/unchecked siblings, drop counterfactuals and closing-question answers remain in `independent-verdicts.md`. Highest-priority deciding checks remain the isolated entrant-history reproduction/control and explicit-settlement benchmark reproduction/control after dependency and filesystem-isolation preflight passes.
