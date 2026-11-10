# Cumulative coverage — 10 November 2026

Source `9913f94b9b795bd9633a6a683e9f420301e400b3`; 111 tracked files: 47 reviewed, 15 partially reviewed, 11 checked automatically, 16 inventoried and 22 blocked. Exact ranges remain in [coverage-map.json](coverage-map.json).

This Tuesday mining visit added 721 cumulative semantic lines. Discretionary reading was exactly 175 exploitation and 175 exploration lines, plus 371 mandatory caller/consumer lines. `invest_mining/cli.py` is now fully semantically covered at the current blob, and `tests/test_ledger.py` advanced through lines 201–329 and 356–401. Remaining unread scope is 16,591 lines across 59 paths.

Behavioral evidence was not refreshed on this worker because credential isolation and the exact installed locked graph were not proven. The six successful same-SHA GitHub checks are reused only for their original scope. Peer head `f73a1d1` has no new exact-range mining finding for this question.

Whole-repository coverage remains incomplete.
