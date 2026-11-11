# Cumulative coverage — 11 November 2026

Source `9913f94b9b795bd9633a6a683e9f420301e400b3`; 111 tracked files: 49 reviewed, 15 partially reviewed, 11 checked automatically, 14 inventoried and 22 blocked. Exact ranges remain in [coverage-map.json](coverage-map.json).

This Wednesday evaluation visit added **371 cumulative semantic lines**. Discretionary reading was 188 exploitation and 209 exploration lines, plus 77 caller/contract lines. `invest_evaluation/cli.py` and `strategy-evaluation/README.md` are now fully covered at their current blobs. `tests/test_engine.py` advanced through settlement accounting at lines 231–272 and universe-benchmark missing-session behavior at 523–557. Remaining known unread scope is 16,220 lines across 57 paths.

Behavioral evidence was not refreshed on this worker because credential isolation and the exact installed locked graph were not proven. Six successful same-SHA GitHub checks are reused only from preserved evidence. Peer head `f73a1d1` supplies a same-SHA settlement-benchmark runtime corroboration, not execution by this audit.

Whole-repository coverage remains incomplete. Other fields are not scheduled today.
