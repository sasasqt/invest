# Cumulative coverage — 5 November 2026

Source `9913f94b9b795bd9633a6a683e9f420301e400b3`; {'tracked_files': 111, 'bytes_verified_files': 16, 'primary_semantic_lines': 2053, 'primary_by_bucket': {'exploitation': 409, 'exploration': 414, 'mandatory_callers_contracts': 1230}, 'helper_lines_separate': 1082, 'new_cumulative_lines_all_reviewers': 1289, 'statuses': {'reviewed': 42, 'inventoried': 16, 'partially_reviewed': 18, 'checked_automatically': 13, 'blocked': 22}, 'unread_lines': 18071, 'unread_paths': 64}

GPT exact ranges are preserved in coverage-map.json. Peer exact byte/range union is unavailable. Per-file branch coverage unavailable for this static visit; existing runtime coverage is historical. Last28day records remain in review_history; no old byte identities were promoted to current behavior.

Least covered current files: .gitignore, README.md, ROADMAP.md, data-mining-framework/LITERATURE_REVIEW.md, data-mining-framework/PRIMARY_SOURCE_CATALOG.md, data-mining-framework/src/invest_mining/__init__.py, data-mining-framework/src/invest_mining/reporting.py, data-mining-framework/tests/conftest.py, data-mining-framework/tests/test_cli.py, data-mining-framework/tests/test_diagnostics.py.

Category totals and 28-day file-date status, with unknown per-range recency made explicit: [coverage-age.json](2026-11-05-integration/coverage-age.json).


## 6 November engineering scope

Product-main coverage counts remain unchanged: today's bounded question inspected unmerged runner refs, not new `9913f94b9b795bd9633a6a683e9f420301e400b3` product lines. Byte identities were verified for `runner_workload.py`, `verify_installed.py`, `Dockerfile` and `audit-runtime.yml` at both `cd4d43b48a8c86fc58299aa50cac88b28c508b5e` and `e0181fcbfda9814c53bccec4d0f1d5294487ec2d`. Primary semantic reading: 359 exploitation lines, 246 exploration lines and 195 mandatory contract lines; helper reading is not added to the denominator. Whole-repository coverage remains incomplete.
