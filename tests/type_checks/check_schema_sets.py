"""Type tests: the dataset kinds, factor evidence sets and portfolio verdict statuses.

mypy checks this file; nothing runs it. Each line uses a value the set leaves out, so its
``# type: ignore`` is needed only while the set's ``Literal`` type holds: a call fails with
``arg-type``, and comparing an element of a ``Literal``-typed tuple with it fails with
``comparison-overlap`` (strict equality; mypy reads the left side of ``in`` as ``str``, so a
membership test would not show it). If a parameter or tuple goes back to ``str``, mypy
reports the ignore as unused.
"""

from invest_data.bundle import Manifest
from invest_data.schemas import (
    ADJUSTED_PRICES,
    FACTOR_EVIDENCE_SOURCES,
    FACTOR_STATUSES,
    FACTOR_TEST_OUTCOMES,
    PRICE_ADJUSTMENTS,
    _check_kind,
    _check_metadata,
    _validate_metadata,
)
from invest_evaluation.validation import PORTFOLIO_STATUSES


def _never_called(manifest: Manifest) -> list[bool]:
    _check_kind(manifest, "bars")  # type: ignore[arg-type]
    _validate_metadata({}, (), "bars")  # type: ignore[arg-type]
    _check_metadata(manifest, (), "bars")  # type: ignore[arg-type]
    return [
        PRICE_ADJUSTMENTS[0] == "raw",  # type: ignore[comparison-overlap]
        ADJUSTED_PRICES[0] == "split_adjusted",
        FACTOR_TEST_OUTCOMES[0] == "passed",  # type: ignore[comparison-overlap]
        FACTOR_STATUSES[0] == "passed",  # type: ignore[comparison-overlap]
        FACTOR_EVIDENCE_SOURCES[0] == "manual",  # type: ignore[comparison-overlap]
        PORTFOLIO_STATUSES[0] == "passed",  # type: ignore[comparison-overlap]
    ]
