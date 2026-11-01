#!/usr/bin/env bash
# Check: two test sites use pandas behaviour that pandas 3.1 deprecates with Pandas4Warning ("will raise an error in a
# future version"): test_cleaning_and_sources.py:116 (setting an incompatible dtype item) and tests/test_pipeline.py:266
# (read_csv float_precision=). CI's wheels and independent-install jobs install unpinned pandas (3.1.0 today), so these
# tests will fail there when pandas 4 ships; the locked environment (pandas 3.0.6) emits nothing.
# Usage: ra_pandas4_deprecations_in_tests.sh <python with pandas>=3.1> <main worktree>
# Exit 0 = no deprecation warning raised as error, 1 = the tests fail with -W error::pandas.errors.Pandas4Warning, 2 = setup error.
set -uo pipefail
PY="${1:?python}"; M="${2:?worktree}"
"$PY" -c "import pandas, pandas.errors; print('pandas', pandas.__version__); pandas.errors.Pandas4Warning" || { echo "setup error: pandas.errors.Pandas4Warning missing (pandas < 3.1?)"; exit 2; }
cd "$M" || exit 2
"$PY" -m pytest -p no:cacheprovider -q -W error::pandas.errors.Pandas4Warning \
  "data-pipeline/data-preparation/tests/test_cleaning_and_sources.py::test_as_traded_close_is_optional_and_validated" \
  "tests/test_pipeline.py::test_historical_workflow_script_replays_snapshot_offline" 2>&1 | tail -15
rc=${PIPESTATUS[0]}
if [ "$rc" -eq 0 ]; then echo "PASS: no Pandas4Warning raised"; exit 0; fi
echo "FAIL: the tests raise Pandas4Warning under pandas $("$PY" -c 'import pandas; print(pandas.__version__)') (exit $rc)"; exit 1
