#!/usr/bin/env bash
# Same-host A/B control: synth-M on 2edd7ae (last audited main) vs eb64ad8 (this main), 3 reps each, after s5.
set -u
S=/tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad
W=/mnt/project-files/review/repo-audit/work/2026-11-22
TOOLS=/mnt/project-files/review/repo-audit/tools
L=$W/s5; RAW=$L/control_raw.jsonl
log(){ echo "$(date -u +%FT%TZ) [control] $*" >> $L/driver.log; }
cd $S/main
[ -d $S/ctl ] || git worktree add --detach $S/ctl 2edd7ae1168eda1192ff73698ba5d42a7c034a41 > $L/control_worktree.log 2>&1
cd $S/ctl && uv sync --frozen >> $L/control_worktree.log 2>&1; log "ctl uv sync rc=$?"
for side in ctl:2edd7ae1168eda1192ff73698ba5d42a7c034a41:$S/ctl main:$(cat $W/main_sha_full.txt):$S/main; do
  n=${side%%:*}; rest=${side#*:}; sha=${rest%%:*}; wt=${rest#*:}
  log "start synth-M-$n reps=3"
  python3 -I $TOOLS/bench.py run --raw $RAW --run-id control-2026-11-22 --date 2026-11-22 --sha $sha --case synth-M-$n --reps 3 --cwd $wt --out-dir $S/bench-ctl/synth-M-$n --lockfile $wt/uv.lock --env "PATH=$wt/.venv/bin:$PATH" --input INSTRUMENTS=60 --input DAYS=750 --input TRIALS=200 --hash-exclude mining/ledger.jsonl --hash-exclude 'quantiles/tables/*.csv.gz' --timeout 1800 -- scripts/synthetic_workflow.sh $S/bench-ctl/synth-M-$n > $L/control-$n.log 2>&1
  log "done synth-M-$n rc=$?"
done
cd $S/ctl && git status --porcelain > $L/control_git_status.txt
echo done > $L/control.status
