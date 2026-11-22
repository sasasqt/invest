# Repo audit handoffs (Claude)

Decisions and actions of the handoff gate (live instructions v5 and later, step 7b; the user's rule of 2026-11-18). Rows are never deleted and are written only by the weekly repo audit. A receiving routine reads this file from the head of `claude/repo-audits`; the mirror carries it to `main`. Every open or plausible row of `findings.md` and every open row of `recommendations.md` carries its Route there.

| Handoff ID | RA ID | Kind | Title | Decided | Gate evidence | Routed to | Action asked | Action taken | Status |
|---|---|---|---|---|---|---|---|---|---|

2026-11-22 (first run under the gate, main eb64ad8): no row met every condition of `handed-off` (kept by both reviewers, GPT "agree" after First seen, a saved check failing on main, a routine as owner, effort S or M), so no handoff was made. Routes this run: findings: 2 `in-pr` (RA-2026-11-01-2 PR #73, RA-2026-11-08-1 PR #66), 4 `needs-user` (RA-2026-11-01-3, RA-2026-11-08-2, RA-2026-11-08-3, RA-2026-11-15-1: GPT "cannot check" or no verdict in 2 or more reports), 3 `done`; recommendations: 2 `in-pr`, 2 `todo` (RA-2026-11-01-10, RA-2026-11-01-11), 10 `needs-user`, 2 `done`, 1 `waiting-gpt` (RA-2026-11-22-1, new).
