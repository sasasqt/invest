#!/usr/bin/env bash
# s5 benchmarks, repo audit 2026-11-22. Runs every case through TOOLS/bench.py from $S/main.
set -u
S=/tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad
W=/mnt/project-files/review/repo-audit/work/2026-11-22
OUT=$S/audits/audits/claude
TOOLS=/mnt/project-files/review/repo-audit/tools
SHA=$(cat $W/main_sha_full.txt)
L=$W/s5
log(){ echo "$(date -u +%FT%TZ) $*" >> $L/driver.log; }
cd $S/main
git status --porcelain > $L/git_status_before_s5.txt
COMMON=(--raw $OUT/benchmarks/raw.jsonl --run-id repo-audit-2026-11-22 --date 2026-11-22 --sha $SHA --cwd $S/main --lockfile $S/main/uv.lock --env "PATH=$S/main/.venv/bin:$PATH" --hash-exclude mining/ledger.jsonl --hash-exclude 'quantiles/tables/*.csv.gz' --timeout 1800 --fingerprint-out $L/fingerprint.json)
synth(){ # case reps inst days trials pass_env
  local c=$1 r=$2 i=$3 d=$4 t=$5 pe=$6 envs=()
  if [ "$pe" = 1 ]; then envs=(--env INSTRUMENTS=$i --env DAYS=$d --env TRIALS=$t); fi
  log "start $c reps=$r"
  python3 -I $TOOLS/bench.py run "${COMMON[@]}" --case $c --reps $r --out-dir $S/bench/$c "${envs[@]}" --input INSTRUMENTS=$i --input DAYS=$d --input TRIALS=$t -- scripts/synthetic_workflow.sh $S/bench/$c > $L/$c.log 2>&1
  log "done $c rc=$?"
}
synth synth-S 7 20 300 20 1
synth synth-M 7 60 750 200 0
synth synth-L 3 120 1500 200 1
LMED=$(python3 -I -c "
import json,statistics,sys
w=[r['wall_s'] for r in map(json.loads,open('$OUT/benchmarks/raw.jsonl')) if r.get('run_id')=='repo-audit-2026-11-22' and r.get('case')=='synth-L' and not r.get('warmup') and r.get('rc')==0]
print(statistics.median(w) if w else 9999)")
log "synth-L median wall_s=$LMED"
if python3 -c "import sys; sys.exit(0 if float('$LMED') < 90 else 1)"; then synth synth-XL 1 240 3000 200 1; else log "synth-XL skipped (synth-L median >= 90 s)"; fi
for f in csv sqlite parquet; do
  log "start formats-$f reps=3"
  python3 -I $TOOLS/bench.py run "${COMMON[@]}" --case formats-$f --reps 3 --out-dir $S/bench/formats-$f --env INSTRUMENTS=60 --env DAYS=750 --env TRIALS=20 --env FORMAT=$f --env ROOT=$S/main --input INSTRUMENTS=60 --input DAYS=750 --input TRIALS=20 --input FORMAT=$f -- $S/scripts/formats_case.sh $S/bench/formats-$f > $L/formats-$f.log 2>&1
  log "done formats-$f rc=$?"
done
cp $S/main/ledgers/yahoo-test.jsonl $S/bench/ledger-replay.jsonl
sha256sum $S/main/ledgers/yahoo-test.jsonl > $L/ledger_sha_before.txt
ARCH=$(sha256sum /mnt/project-files/data/yahoo-test/snapshot-2026-10-07T1032Z.tgz | cut -d' ' -f1)
log "start real-replay reps=1"
python3 -I $TOOLS/bench.py run "${COMMON[@]}" --case real-replay --reps 1 --out-dir $S/bench/real-replay --env SNAPSHOT=$S/s4/snap/snapshot --env LEDGER=$S/bench/ledger-replay.jsonl --input SNAPSHOT=2026-10-07T1032Z --snapshot-sha256 $ARCH -- scripts/historical_workflow.sh $S/bench/real-replay > $L/real-replay.log 2>&1
log "done real-replay rc=$?"
sha256sum $S/main/ledgers/yahoo-test.jsonl > $L/ledger_sha_after.txt
cmp -s $L/ledger_sha_before.txt $L/ledger_sha_after.txt && log "tracked ledger unchanged" || log "tracked ledger CHANGED"
git status --porcelain > $L/git_status_after_s5.txt
python3 -I $TOOLS/bench.py summarize --raw $OUT/benchmarks/raw.jsonl --run-id repo-audit-2026-11-22 --out $OUT/benchmarks/history.md --json $L/summary.json --scaling-cases synth-S,synth-M,synth-L,synth-XL > $L/summarize.log 2>&1
log "summarize rc=$?"
echo done > $L/ALL.status
