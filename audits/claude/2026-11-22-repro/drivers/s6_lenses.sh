#!/usr/bin/env bash
# s6 lenses on synth-M (bench output of the last repetition = repetition 1 by the gate) and the replay at main.
set -u
S=/tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad
W=/mnt/project-files/review/repo-audit/work/2026-11-22
OUT=$S/audits/audits/claude
C=$W/checks
PY=$S/main/.venv/bin/python
M=$S/bench/synth-M
R=$S/s4/replay-main
log(){ echo "$(date -u +%FT%TZ) $*" >> $C/lenses.log; }
cd $S/scratch_lens 2>/dev/null || { mkdir -p $S/scratch_lens; cd $S/scratch_lens; }
run(){ local name=$1; shift; "$@" > $C/$name.txt 2>&1; log "$name rc=$?"; }
log "start (synth-M at $M, replay at $R)"
# rf/MAR evaluation of synth-M (as 2026-11-15)
rm -rf $S/s6/eval-rf-mar; mkdir -p $S/s6
PATH=$S/main/.venv/bin:$PATH invest-eval run --data $M/data/market --universe $M/data/universe --signals $M/signals --config $OUT/2026-11-15-repro/config_rf_mar.json --out $S/s6/eval-rf-mar > $C/eval_rf_mar.log 2>&1; log "eval rf-mar rc=$?"
for d in synth-M:$M/eval replay-main:$R/eval rf-mar:$S/s6/eval-rf-mar; do
  n=${d%%:*}; p=${d#*:}
  run lens_accounting.$n $PY -I $OUT/2026-11-15-repro/lens_accounting.py $p
  run recompute_metrics.$n $PY -I $OUT/2026-11-08-repro/recompute_metrics.py $p
done
run report_vs_metrics.synth-M $PY -I $OUT/2026-11-08-repro/report_vs_metrics.py $M/eval
run report_vs_metrics.replay-main $PY -I $OUT/2026-11-08-repro/report_vs_metrics.py $R/eval
run rerun_ra_2026_11_01_4_censored.synth-M $PY -I $OUT/2026-11-01-repro/ra_report_omits_censored_drawdown_duration.py $M/eval
run rerun_ra_2026_11_08_3_window.synth-M $PY -I $OUT/2026-11-08-repro/ra_report_omits_evaluation_window.py $M/eval
run lens_formats $PY -I $OUT/2026-11-08-repro/lens_formats.py $S/bench
run rerun_ra_2026_11_01_10_gzip_mtime $PY -I $OUT/2026-11-01-repro/ra_gzip_tables_carry_wall_clock_mtime.py $R/quantiles $S/bench/real-replay/quantiles
run uncovered_decision_branches.run1 $PY -I $C/uncovered_decision_branches.py
run uncovered_decision_branches.run2 $PY -I $C/uncovered_decision_branches.py
# timing lens v3 (T and confirm start chosen from synth-M's calendar by timing_dates.py)
read T CS < <($PY -I -c "
import pandas as pd
from invest_data.schemas import read_market_bars
_, b = read_market_bars('$M/data/market'); s = sorted(b['date'].unique())
print(pd.Timestamp(s[int(len(s)*0.8)]).date(), pd.Timestamp(s[int(len(s)*0.7)]).date())")
log "timing v3 T=$T confirm_start=$CS"
run lens_timing_v3 $PY -I $C/lens_timing_v3.py $M $S/s6/timing-v3 $T $CS $S/main/strategy-evaluation/examples/quantile_long_short.json $S/main/.venv/bin
log "done"
echo done > $C/lenses.status
