#!/usr/bin/env bash
# Reserved-window and reuse paths through the CLIs on the synthetic market (2020-01-01..2022-11-15),
# with a ledger copy in this folder. Prints each command's exit code and the key output.
set -u
R=${OUT:?set OUT to a scratch folder}
B=${INVEST:?set INVEST to an invest checkout at eb64ad8}/.venv/bin
D=$R/syn
W=$R/ledger/work
rm -rf "$W"; mkdir -p "$W"
L=$W/ledger.jsonl
run() { echo "--- $*"; "$@" > "$W/last.out" 2>&1; echo "exit $?"; tail -3 "$W/last.out"; }
run $B/invest-mine ledger reserve --ledger "$L" --start 2022-01-03 --note "test reservation"
run $B/invest-mine evaluate --data $D/market --expr "close / delay(close, 5) - 1" --ledger "$L" --out $W/eval1
run $B/invest-mine search --data $D/market --universe $D/universe --trials 10 --ledger "$L" --out $W/s_overlap
run $B/invest-mine search --data $D/market --universe $D/universe --trials 10 --confirm-start 2022-01-10 --ledger "$L" --out $W/s_late
run $B/invest-mine search --data $D/market --universe $D/universe --trials 10 --confirm-start 2022-01-03 --ledger "$L" --out $W/s1
run $B/invest-mine search --data $D/market --universe $D/universe --trials 10 --seed 1 --confirm-start 2022-01-03 --ledger "$L" --out $W/s2
run $B/invest-mine search --data $D/market --universe $D/universe --trials 10 --seed 1 --confirm-start 2022-01-03 --ledger "$L" --require-confirmatory --out $W/s3
run $B/invest-mine freeze --expr "ts_mean(returns, 10)" --horizon 1 --out $W/f.json
run $B/invest-mine confirm --data $D/market --universe $D/universe --factor $W/f.json --confirm-start 2022-01-03 --ledger "$L" --out $W/c1
run $B/invest-mine export --data $D/market --universe $D/universe --from-search $W/s2 --out $W/sig_s2
python3 -c "import json;e=json.load(open('$W/sig_s2/manifest.json'))['metadata']['factor_evidence'];print('s2 evidence:',e['confirmation_use'],e['status'],e['test_outcome'])"
run $B/invest-mine export --data $D/market --universe $D/universe --from-search $W/s1 --out $W/sig_s1
python3 -c "import json;e=json.load(open('$W/sig_s1/manifest.json'))['metadata']['factor_evidence'];print('s1 evidence:',e['confirmation_use'],e['status'],e['test_outcome'])"
echo "--- ledger entries:"
python3 -c "
import json
for l in open('$L'):
    e=json.loads(l); print(e['kind'], e.get('window') or (e.get('development'), e.get('confirmation')), e.get('confirmation_use'), e.get('n_proposals'))"
