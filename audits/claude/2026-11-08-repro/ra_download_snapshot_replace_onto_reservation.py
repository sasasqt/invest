"""Check: `download_snapshot` reserves its destination with `root.mkdir()` and then publishes the staged
snapshot with `os.replace(stage, root)` (invest_data/yahoo.py:192, 230). On Windows, MoveFileEx with
MOVEFILE_REPLACE_EXISTING cannot replace an existing directory (the API refuses it when either name is a
directory), so the publish step raises PermissionError and every Yahoo download fails there. scripts/save_run.py
knows this ("Windows rename already refuses any existing destination") and reserves only on POSIX.

No Windows host here: this check runs the download under a stand-in for Windows semantics, as the repo's own
tests/test_save_run.py `windows_rename` fixture does. `os.replace` is wrapped to refuse a directory destination
that exists (and to behave as on POSIX otherwise). The control is the same download without the wrapper.

Usage: python ra_download_snapshot_replace_onto_reservation.py <tmp dir>
Exit 0 when the download publishes under Windows semantics, 1 when it fails (the finding), 2 on setup error.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

try:
    from invest_data import yahoo
    from invest_data.sources import SyntheticConfig, synthetic_market
    from invest_data.testing import fake_chart
except Exception as exc:  # pragma: no cover
    print("setup error:", exc)
    sys.exit(2)

tmp = Path(sys.argv[1])
if tmp.exists():
    shutil.rmtree(tmp)
tmp.mkdir(parents=True)
good = json.dumps(fake_chart(synthetic_market(SyntheticConfig(n_instruments=1, n_days=5, seed=3)), "AAA")).encode()
fetcher = lambda url, timeout: good  # noqa: E731

# Control: POSIX semantics publish the snapshot.
yahoo.download_snapshot(["AAA"], "2020-01-01", "2020-02-01", tmp / "posix", fetcher=fetcher)
if not (tmp / "posix" / "snapshot.json").is_file():
    print("setup error: control download did not publish")
    sys.exit(2)

real_replace = os.replace


def windows_replace(src, dst, *args, **kwargs):
    """MoveFileExW(MOVEFILE_REPLACE_EXISTING) refuses an existing destination when a directory is involved."""
    if Path(src).is_dir() and Path(dst).exists():
        raise PermissionError(5, "Access is denied (Windows: cannot replace an existing directory)", str(dst))
    return real_replace(src, dst, *args, **kwargs)


yahoo.os.replace = windows_replace
try:
    yahoo.download_snapshot(["AAA"], "2020-01-01", "2020-02-01", tmp / "win", fetcher=fetcher)
except PermissionError as exc:
    print(f"FAIL: download_snapshot cannot publish under Windows rename semantics: {exc}")
    print(f"      destination left behind: {sorted(p.name for p in tmp.iterdir())}")
    sys.exit(1)
finally:
    yahoo.os.replace = real_replace
if (tmp / "win" / "snapshot.json").is_file():
    print("PASS: the snapshot published under Windows rename semantics")
    sys.exit(0)
print("FAIL: no snapshot.json published")
sys.exit(1)
