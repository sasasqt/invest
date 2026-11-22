#!/bin/bash
# Credits each list in $W/s8/credit/<lens>.<status>.txt to the coverage map (rule 31: saved driver).
set -euo pipefail
OUT="$1"; W="$2"; TOOLS="$3"
declare -A REASON=(
 [config]="s2 config checks: uv lock --check, pyproject consistency, CI pins/permissions/triggers"
 [ci-parity]="s2/s3 local jobs vs GitHub CI run 44246922942 on eb64ad8"
 [tests-run]="s3 full suite on 3.11 and 3.13 with branch coverage"
 [test-quality]="s6 rotation slice (6 new test files, 1,411 lines) and verify_installed.py draw"
 [deep-read]="s6 deep read of files changed since 2edd7ae and their callers (lenses, branch check)"
 [saved-results]="s4 replay of the committed run record at c6f2961 and at main eb64ad8"
 [workflow]="s2 workflow read of ci.yml, docs.yml and audit-runtime.yml"
 [benchmark]="s5 benchmark cases and same-host A/B control 2edd7ae vs eb64ad8"
 [bug-hunt-deep-pass]="bug hunt reports 2026-11-16 to 2026-11-20 name these components as deep-passed (read-only)"
 [docs-audit]="docs audit 2026-11-21 report covers these docs (read-only)"
 [cross-check]="s7 GPT cross-check: files GPT findings name, re-checked on main"
)
for f in "$W"/s8/credit/*.txt; do
  b=$(basename "$f" .txt); lens=${b%%.*}; status=${b#*.}
  python3 -I "$TOOLS/coverage_map.py" credit --map "$OUT/coverage-map.json" --date 2026-11-22 \
    --run-id repo-audit-2026-11-22 --status "$status" --lens "$lens" --reason "${REASON[$lens]}" --from-file "$f"
done
