"""Typing helpers shared by the package's modules (private)."""

from __future__ import annotations

from typing import Never


def unhandled(value: Never, error: BaseException) -> BaseException:
    """The error for a value outside a closed set, to ``raise`` at the end of a chain.

    ``value`` is typed ``Never``: once every member of the set has a branch, mypy accepts
    the call, and a new member without a branch fails type checking. A caller that skips
    type checking can still pass any value at run time and gets ``error`` unchanged.
    """
    return error  # pragma: no cover
