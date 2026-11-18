"""`invest-data yahoo publish --exclude`, offline, on a fabricated snapshot."""

from pathlib import Path

import pytest

from invest_data.cli import main
from invest_data.schemas import read_market_bars
from invest_data.sources import SyntheticConfig, synthetic_market
from invest_data.testing import write_fake_snapshot


@pytest.mark.parametrize(
    "selection,expected",
    [
        ([], {"SYN000", "SYN002"}),  # every snapshot symbol but the excluded one
        (["--symbols", "SYN000", "SYN001"], {"SYN000"}),  # the named ones but the excluded one
    ],
    ids=["whole-snapshot", "named-symbols"],
)
def test_publish_leaves_out_the_excluded_symbols(
    tmp_path: Path, selection: list[str], expected: set[str]
) -> None:
    bars = synthetic_market(SyntheticConfig(n_instruments=3, n_days=10, seed=3))
    write_fake_snapshot(bars, tmp_path / "snap")
    out = tmp_path / "bundle"
    args = ["--snapshot", str(tmp_path / "snap"), "--out", str(out), "--dataset-id", "y"]
    assert main(["yahoo", "publish", *args, *selection, "--exclude", "SYN001"]) == 0
    manifest, frame = read_market_bars(out)
    assert set(frame["instrument"]) == expected
    assert manifest.provenance["selection"]["symbols"] == sorted(expected)
