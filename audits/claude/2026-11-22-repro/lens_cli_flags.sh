#!/usr/bin/env bash
# Exploration lens: every --flag a doc writes after an invest-* subcommand exists in that subcommand's --help.
# usage: bash lens_cli_flags.sh <worktree> ; exit 1 if a documented flag is missing from --help
set -uo pipefail
root=$1; bin=$root/.venv/bin; rc=0
cd "$root"
python3 - "$root" > /tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad/doc_cmds.txt <<'PY'
import re, subprocess, sys
root=sys.argv[1]
files=[f for f in subprocess.run(["git","-C",root,"ls-files","*.md","*.sh"],capture_output=True,text=True).stdout.split() if not f.startswith(("docs/audits/","runs/"))]
for f in files:
    text=open(f"{root}/{f}",encoding="utf-8").read().replace("\\\n"," ")
    for m in re.finditer(r"(invest-(?:mine|eval|data))\s+([a-z-]+)(?:\s+([a-z|]+))?([^\n`]*)", text):
        tool, sub, sub2, rest = m.groups()
        flags=sorted(set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", rest)))
        subs=[sub]
        if sub=="yahoo" and sub2: subs=[sub+" "+s for s in sub2.split("|")]
        if sub=="ledger" and sub2: subs=[sub+" "+s for s in sub2.split("|")]
        for s in subs:
            print(f"{f}\t{tool}\t{s}\t{' '.join(flags)}")
PY
sort -u /tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad/doc_cmds.txt | while IFS=$'\t' read -r f tool sub flags; do
  help=$($bin/$tool $sub --help 2>&1) || { echo "NOHELP $f: $tool $sub"; continue; }
  for fl in $flags; do
    if ! grep -q -- "$fl\b" <<< "$help"; then echo "MISSING $f: $tool $sub $fl"; rc=1; fi
  done
done
exit $rc
