#!/usr/bin/env bash
# s4: replay the saved record at its revision and at main (offline, temporary ledger copies).
set -uo pipefail
S=/tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad
W=/mnt/project-files/review/repo-audit/work/2026-11-22/s4
T=/mnt/project-files/review/repo-audit/tools
REC=runs/yahoo-test/2026-10-07
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> $W/driver.log; }
log "s4 start"
mkdir -p $S/s4/snap
sha256sum /mnt/project-files/data/yahoo-test/snapshot-2026-10-07T1032Z.tgz > $W/archive_sha256.txt
tar -xzf /mnt/project-files/data/yahoo-test/snapshot-2026-10-07T1032Z.tgz -C $S/s4/snap
SNAP=$S/s4/snap/snapshot
if cmp -s $SNAP/snapshot.json $S/main/$REC/snapshot/snapshot.json; then log "snapshot.json identical to record"; else log "snapshot.json DIFFERS from record"; fi
sha256sum $SNAP/snapshot.json $S/main/$REC/snapshot/snapshot.json >> $W/archive_sha256.txt
REV=$(grep -o 'Code revision | `[0-9a-f]*' $S/main/$REC/README.md | grep -o '[0-9a-f]\{40\}')
log "recorded revision $REV"
cd /home/user/invest && git worktree add --detach $S/rec $REV >> $W/driver.log 2>&1
cd $S/rec && UV_PROJECT_ENVIRONMENT=$S/rec/.venv uv sync --frozen > $W/sync-rec.log 2>&1; log "sync rec rc=$?"
cp $S/rec/ledgers/yahoo-test.jsonl $S/s4/ledger-rec.jsonl
cp $S/main/ledgers/yahoo-test.jsonl $S/s4/ledger-main.jsonl
sha256sum $S/s4/ledger-rec.jsonl $S/s4/ledger-main.jsonl $S/main/ledgers/yahoo-test.jsonl > $W/ledger_sha_before.txt
t0=$(date +%s)
cd $S/rec && SNAPSHOT=$SNAP LEDGER=$S/s4/ledger-rec.jsonl uv run scripts/historical_workflow.sh $S/s4/replay-rec > $W/replay-rec.log 2>&1; rc=$?
log "replay-rec rc=$rc secs=$(( $(date +%s)-t0 ))"
t0=$(date +%s)
cd $S/main && SNAPSHOT=$SNAP LEDGER=$S/s4/ledger-main.jsonl uv run scripts/historical_workflow.sh $S/s4/replay-main > $W/replay-main.log 2>&1; rc=$?
log "replay-main rc=$rc secs=$(( $(date +%s)-t0 ))"
sha256sum $S/s4/ledger-rec.jsonl $S/s4/ledger-main.jsonl $S/main/ledgers/yahoo-test.jsonl > $W/ledger_sha_after.txt
python3 -I $T/compare_record.py $S/main/$REC $S/s4/replay-rec --report $W/compare-rec.md --json $W/compare-rec.json > $W/compare-rec.out 2>&1; log "compare-rec rc=$?"
python3 -I $T/compare_record.py $S/main/$REC $S/s4/replay-main --report $W/compare-main.md --json $W/compare-main.json > $W/compare-main.out 2>&1; log "compare-main rc=$?"
git -C $S/rec status --porcelain > $W/git_status_rec_after.txt
git -C $S/main status --porcelain > $W/git_status_main_after.txt
log "s4 ALL DONE"
echo done > $W/ALL.status
