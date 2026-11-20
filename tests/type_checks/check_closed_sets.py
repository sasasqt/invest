"""Type tests: a value outside a closed set fails type checking.

mypy checks this file; nothing runs it. Each call passes a value the set leaves out, so
its ``# type: ignore`` is needed only while the parameter's ``Literal`` type holds; if
the parameter goes back to ``str``, mypy reports the ignore as unused.
"""

import pandas as pd

from invest_data.bundle import Column, write_bundle
from invest_evaluation.config import ValidationConfig
from invest_evaluation.quantiles import BucketPortfolio
from invest_evaluation.strategies import Slice
from invest_evaluation.validation import _check
from invest_mining import ledger
from invest_mining.diagnostics import daily_ic
from invest_mining.expressions import OpSpec
from invest_mining.search import mark_confirmation_use


def _never_called(frame: pd.DataFrame) -> None:
    Slice("middle", 0.1)  # type: ignore[arg-type]
    BucketPortfolio("x", "short_only", Slice("top", 0.1))  # type: ignore[arg-type]
    daily_ic(frame, frame, method="kendall")  # type: ignore[arg-type]
    _check("sessions", "passed", 1, "> 0", "daily net returns")  # type: ignore[arg-type]
    Column("volume", "integer")  # type: ignore[arg-type]
    write_bundle(frame, "out", dataset_id="d", fmt="json")  # type: ignore[arg-type]
    ledger.append("ledger.jsonl", "reserve", {})  # type: ignore[arg-type]
    ValidationConfig(benchmark="spy")  # type: ignore[arg-type]
    OpSpec("ternary", lambda x: x)  # type: ignore[arg-type]
    mark_confirmation_use(frame, "maybe")  # type: ignore[arg-type]
