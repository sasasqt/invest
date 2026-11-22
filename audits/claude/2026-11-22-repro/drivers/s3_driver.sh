#!/usr/bin/env bash
# s3 test matrix driver: reproduces every ci.yml job locally (at most 3 at a time).
set -uo pipefail
S=/tmp/claude-0/-home-user/9df18979-85cf-58fb-90b6-6a2d32ff7623/scratchpad
W=/mnt/project-files/review/repo-audit/work/2026-11-22
T=$W/tests
M=$S/main
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> $T/driver.log; }
cd $M
log "s3 start"
t0=$(date +%s); uv sync --frozen > $T/uv_sync.log 2>&1; rc=$?; log "uv sync --frozen rc=$rc secs=$(( $(date +%s)-t0 ))"

checks() {  # $1 = label, $2 = env dir (empty = .venv), $3 = python
  local lab=$1 envdir=$2 py=$3 L=$T/$1
  mkdir -p $L
  export COVERAGE_FILE=$L/.coverage MYPY_CACHE_DIR=$S/cache/$lab/mypy RUFF_CACHE_DIR=$S/cache/$lab/ruff
  if [ -n "$envdir" ]; then export UV_PROJECT_ENVIRONMENT=$envdir; fi
  local pyarg=""; [ -n "$py" ] && pyarg="--python $py"
  local t0=$(date +%s)
  run() { local name=$1; shift; local s=$(date +%s); "$@" > $L/$name.log 2>&1; local rc=$?; echo "$name,$rc,$(( $(date +%s)-s ))" >> $L/steps.csv; return 0; }
  run sync uv sync --frozen $pyarg
  run ruff_format uv run $pyarg ruff format --check .
  run ruff_check uv run $pyarg ruff check .
  run mypy uv run $pyarg mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src scripts
  run pytest uv run $pyarg pytest -p no:cacheprovider --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch --cov-report=term-missing --cov-report=json:$L/cov.json --durations=25 --junitxml=$L/junit.xml
  run coverage_json uv run $pyarg coverage json -q -o $L/coverage.json
  run floors uv run $pyarg python scripts/check_coverage_floors.py $L/coverage.json
  run md_links uv run $pyarg python scripts/check_markdown_links.py
  uv run $pyarg python -c "import invest_data, invest_mining, invest_evaluation, sys; print(sys.version); [print(m.__name__, m.__file__) for m in (invest_data, invest_mining, invest_evaluation)]" > $L/import_paths.txt 2>&1
  log "$lab done secs=$(( $(date +%s)-t0 ))"
}

wheels() {
  local L=$T/wheels; mkdir -p $L; local t0=$(date +%s)
  rm -rf $S/wheels/dist $S/wheels/venv
  run() { local name=$1; shift; local s=$(date +%s); "$@" > $L/$name.log 2>&1; local rc=$?; echo "$name,$rc,$(( $(date +%s)-s ))" >> $L/steps.csv; return 0; }
  run build uv build --all-packages --out-dir $S/wheels/dist
  run venv uv venv $S/wheels/venv --python /usr/bin/python3.11
  run install bash -c "uv pip install --python $S/wheels/venv $S/wheels/dist/*.whl pytest"
  run cli_smoke bash -c "for cli in invest-data invest-mine invest-eval; do $S/wheels/venv/bin/\$cli --help > /dev/null || exit 1; done"
  (cd $S/wheels && $S/wheels/venv/bin/python -c "import invest_data, invest_mining, invest_evaluation, pandas, sys; print(sys.version, pandas.__version__); [print(m.__name__, m.__file__) for m in (invest_data, invest_mining, invest_evaluation)]") > $L/import_paths.txt 2>&1
  cd $S/wheels
  run pytest $S/wheels/venv/bin/python -m pytest -p no:cacheprovider --rootdir $M --junitxml=$L/junit.xml $M/data-pipeline/data-preparation/tests $M/data-mining-framework/tests $M/strategy-evaluation/tests $M/tests/test_pipeline.py
  cd $M
  ls $S/wheels/dist > $L/dist_list.txt
  log "wheels done secs=$(( $(date +%s)-t0 ))"
}

indep() {  # $1 = component path
  local comp=$1 n=$(basename $1); local L=$T/indep-$n; mkdir -p $L; local t0=$(date +%s)
  local V=$S/ii/$n/venv; rm -rf $S/ii/$n; mkdir -p $S/ii/$n
  run() { local name=$1; shift; local s=$(date +%s); "$@" > $L/$name.log 2>&1; local rc=$?; echo "$name,$rc,$(( $(date +%s)-s ))" >> $L/steps.csv; return 0; }
  cd $M
  run venv uv venv $V --python /usr/bin/python3.11
  run install uv pip install --python $V ./data-pipeline/data-preparation ./$comp pytest
  if [ "$n" = "strategy-evaluation" ]; then
    run no_mining $V/bin/python -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('invest_mining') is not None)"
  fi
  (cd $S/ii && $V/bin/python -c "import importlib, sys; print(sys.version); [print(n, importlib.import_module(n).__file__) for n in ('invest_data','invest_mining','invest_evaluation') if importlib.util.find_spec(n)]") > $L/import_paths.txt 2>&1
  run pytest $V/bin/python -m pytest -p no:cacheprovider --junitxml=$L/junit.xml $comp/tests
  log "indep-$n done secs=$(( $(date +%s)-t0 ))"
}

checks checks313 "" "" &
p1=$!
( checks checks311 $S/venv311 /usr/bin/python3.11 ) &
p2=$!
( wheels ) &
p3=$!
wait $p3
( indep data-pipeline/data-preparation ) &
q1=$!
wait $p2
( indep data-mining-framework ) &
q2=$!
wait $p1
( indep strategy-evaluation ) &
q3=$!
wait $q1 $q2 $q3
# repeat run (hash seed) after the 3.13 checks finished
L=$T/repeat; mkdir -p $L; t0=$(date +%s)
cd $M
PYTHONHASHSEED=12345 uv run pytest -p no:cacheprovider --junitxml=$L/junit.xml > $L/pytest.log 2>&1; echo "pytest,$?,$(( $(date +%s)-t0 ))" >> $L/steps.csv
log "repeat done secs=$(( $(date +%s)-t0 ))"
git -C $M status --porcelain > $T/git_status_after_s3.txt
log "s3 ALL DONE"
echo done > $T/ALL.status
