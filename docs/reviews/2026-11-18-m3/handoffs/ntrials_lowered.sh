#!/usr/bin/env bash
# R2-1 evidence: invest-eval run accepts --n-trials below the signals' recorded n_trials
# when the signals carry no factor_evidence (search factor exported with --factor).
set -u
R=${OUT:?set OUT to a scratch folder}
B=${INVEST:?set INVEST to an invest checkout at eb64ad8}/.venv/bin
CFG=${INVEST:?set INVEST to an invest checkout at eb64ad8}/strategy-evaluation/examples/quantile_long_short.json
cd "$R"
rm -rf r1/out; mkdir -p r1/out
$B/invest-mine export --data syn/market --universe syn/universe \
  --factor syn/search/factors/f_f4031d273d5d.json --out r1/out/signals > /dev/null
$B/invest-eval run --data syn/market --signals r1/out/signals --universe syn/universe \
  --config "$CFG" --out r1/out/eval_default > /dev/null
$B/invest-eval run --data syn/market --signals r1/out/signals --universe syn/universe \
  --config "$CFG" --n-trials 1 --out r1/out/eval_n1 > /dev/null
echo "exit of --n-trials 1 run: $?  (expected: refusal, README.md:149)"
python3 - "$R/r1/out" <<'PY'
import json, sys
root = sys.argv[1]
print("signals metadata n_trials:", json.load(open(f"{root}/signals/manifest.json"))["metadata"]["n_trials"])
for d in ("eval_default", "eval_n1"):
    s = json.load(open(f"{root}/{d}/statistics.json"))["deflated_sharpe"]
    v = json.load(open(f"{root}/{d}/verdict.json"))["portfolio"]
    dsr_check = [c for c in v["checks"] if c["name"] == "deflated_sharpe"][0]
    print(f"{d}: n_trials={s['n_trials']} dsr={s['dsr']:.4f} check={dsr_check['status']} portfolio={v['status']} reasons={v['reasons']}")
PY
