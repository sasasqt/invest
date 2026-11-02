# Approved audit adaptations — 31 October 2026

The approved instruction adaptations are applied to the existing repository-audit task. Its daily 03:00 Europe/Berlin schedule is preserved; the PR-review task and its daily 21:00 schedule are unchanged. The paste-ready prompt is version 2, with a verified hash and a complete requirement map. This is an instruction/runner correction, not a completed repository audit.

## Instructions and scope

The former 96,924-character prompt is consolidated to 91,837 characters. All 363 standing blocks are accounted for: 348 retained verbatim, 15 clarified/editorially consolidated, zero unmapped. Historical drafting references and recovery status overrides move to dated evidence. See [requirement map](2026-10-31-adaptation/instruction-traceability.md) and its digest record.

The instructions retain whole-repository coverage, dedicated primary-source research scouting, independent-review rules, stable root-cause IDs, separate exploration/exploitation allocations, resource limits, reserved-data protections and output-only publication. They explicitly distinguish fresh main input, runner checkout and output-branch identity. The output branch is not synchronized with main. Private Claude paths/model gauges/messaging are not prerequisites. Semantic review credit, impact severity, evidence status, independent-review status and environment health remain separate.

State/checkpoint now persist pending_second_review, open_places and resolution history. The compressed-table correction is queued for a fresh independent review with its actual single-reviewed status; the existing wider format-equivalence work has a concrete next check. No independent reviewer/model was used or claimed in this implementation. No peer ledger, main file, product assertion, dependency lock, other routine or research reservation was changed.

## Comparator correction

The version-1 trusted helper at b4c9a911d0856d1b9c4fd675893d9b61b366414f missed a generated compressed-table numeric mutation while detecting the matching plain-CSV control. The before/after control is retained beside this report. Version 2 decompresses and hashes CSV tables, retains substantive ledger fields/order, normalizes only the declared timestamps/output root, inventories every file, compares declared text and conservative raw bytes for other formats, and records PNG presence/nonempty checks without a pixel-equality claim. Corrupt/truncated gzip fails with retained evidence. Forty targeted tests cover the correction and existing guards.

Per-sample manifests disclose all 38 output files: 34 compared records including both compressed tables and mining/ledger.jsonl, plus four figure-presence checks. All eight manifests in each job were checked against their raw semantic hash; a deduplicated complete manifest template and all per-sample hashes are retained in runtime-evidence.json. Hashing is outside the measured interval.

## Isolated execution

Runner revision: a73149d3cf8df7c133ea436a7787c5d5a2dc88b5 in draft PR #32. Actual PR checkout: abc38c69e5134d5a9d5ab26285691aec5636ef2a; all ten runner/workflow blobs match the stated PR head. Audited source remains 90b5ca038155b97833b120baa57dfecd05d6f641; the separately labeled PR #31 control is a943dbf4a318fc2cb12f93b1d2a875ee51774572. Each artifact digest, 110-source-blob identity, 12 boundary probes, 26 applicable locked versions, installed workspace origins, limits and raw/summary agreement were independently checked by the trusted evidence verifier.

| Job | Full suite | Additional tests | Gate-v2 synth-S median |
|---|---|---|---:|
| [audited / 3.11](https://github.com/sasasqt/invest/actions/runs/41208034002/job/124557059601) | 1 failed, 585 passed in 319.11s (0:05:19) | hash-seed-repeat: 1 failed, 585 passed in 172.90s (0:02:52); data-preparation-tests: 162 passed in 2.84s; data-mining-framework-tests: 1 failed, 128 passed in 27.98s; strategy-evaluation-tests: 240 passed in 81.59s (0:01:21) | 6.880967 s |
| [audited / 3.13](https://github.com/sasasqt/invest/actions/runs/41208034002/job/124557059770) | 1 failed, 585 passed in 234.45s (0:03:54) | not scheduled on 3.13 | 5.372929 s |
| [control / 3.11](https://github.com/sasasqt/invest/actions/runs/41208034002/job/124557059691) | 587 passed in 268.37s (0:04:28) | hash-seed-repeat: 587 passed in 142.63s (0:02:22); data-preparation-tests: 162 passed in 1.73s; data-mining-framework-tests: 130 passed in 23.88s; strategy-evaluation-tests: 240 passed in 68.38s (0:01:08) | 5.828128 s |

All three jobs passed 40 helper tests, all boundary/installed-graph checks, and one warm-up plus seven measured workflows under gate v2. The control passed every validation command. Main's retained failures are solely known INV-COMMON-001 / REVIEW-22; the red baseline is not retried for green status. Regular CI also retained that same failure in four jobs, with data/evaluation independent installs passing. Exact outcomes and original failures are recorded. PR #31 remains separate and unmerged; PR #32 remains a draft.

These are remote Linux/Docker absolute measurements. Hosts/interpreter/library variants and gate versions differ, so no regression/speedup comparison is supported. No peak-memory, M/L/XL or cross-format scaling claim is added. Prior 48 raw invocations remain byte-preserved; 24 version-2 invocations are appended, giving 72 raw invocations across nine jobs. Failed overall runs retain their original status. Full GitHub logs/artifacts have 30-day retention; selected graphs, results, manifest templates and all raw measurements are persisted here.

The audit remains incomplete with 19,659 unread semantic lines across 78 paths and the previously recorded wider workflow, research and historical-replay work. No matching permitted raw archive has been supplied; no reserved 2025-onward observations were accessed. Prior immutable reports remain historical records with their original measurement scope.
