"""Typing helpers shared by the package's modules (private)."""

from __future__ import annotations

from typing import Never


def unhandled(value: Never, error: BaseException) -> BaseException:
    """The error for a value outside a closed set, to ``raise`` at the end of a chain.

    ``value`` is typed ``Never``. While every member of the set has a branch, mypy treats
    the ``raise`` as unreachable and does not check it; a new member without a branch makes
    it reachable, and mypy rejects the call. A caller that skips type checking can still
    pass any value at run time and gets ``error`` unchanged.
    """
    return error  # pragma: no cover
