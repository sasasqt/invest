"""Frozen factors and diagnostics: refusals that no other test reached. Expected messages
are the ones each check documents."""

import json
from pathlib import Path

import pandas as pd
import pytest

from invest_mining.artifact import FrozenFactor
from invest_mining.diagnostics import daily_ic, forward_returns


def _factor(orientation: int = 1) -> FrozenFactor:
    return FrozenFactor(
        expression="returns",
        orientation=orientation,
        horizon_days=1,
        training_start="2024-01-02",
        training_end="2024-06-28",
        dataset_id="d",
        dataset_sha256=None,
    )


@pytest.mark.parametrize("orientation", [0, 2, -2])
def test_a_frozen_factor_refuses_an_orientation_other_than_plus_or_minus_one(
    orientation: int,
) -> None:
    with pytest.raises(ValueError, match=r"orientation must be \+1 or -1"):
        _factor(orientation)


@pytest.mark.parametrize("version", [None, 0, 2, "1"])
def test_loading_a_frozen_factor_refuses_another_artifact_version(
    tmp_path: Path, version: object
) -> None:
    path = _factor().save(tmp_path / "factor.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["artifact_version"] = version
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match=f"unsupported artifact_version {version!r}"):
        FrozenFactor.load(path)


@pytest.mark.parametrize("horizon", [0, -1])
def test_forward_returns_refuse_a_horizon_below_one_session(horizon: int) -> None:
    open_ = pd.DataFrame({"A": [10.0, 11.0, 12.0]})
    with pytest.raises(ValueError, match="horizon must be >= 1"):
        forward_returns(open_, horizon)


def test_daily_ic_refuses_an_unknown_correlation_method() -> None:
    panel = pd.DataFrame({"A": [1.0], "B": [2.0]})
    with pytest.raises(ValueError, match="unknown method 'kendall'"):
        daily_ic(panel, panel, method="kendall")
