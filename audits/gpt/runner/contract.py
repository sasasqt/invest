"""Test-mode checks for the rules in CONTRACT.md.

The checks run only when the environment sets CONTRACT_CHECKS=1. Every test suite,
the CI host steps and the CI Docker controls step set it; production runs do not.
A failed check is a bug in the runner, never a property of the audited input, so it
raises an AssertionError that no collection or staging handler turns into an
ordinary rejection.
"""

import os


class ContractViolation(AssertionError):
    """A CONTRACT.md rule did not hold."""


def enabled():
    return os.environ.get("CONTRACT_CHECKS") == "1"


def require(rule, condition, detail=""):
    if not condition:
        raise ContractViolation(f"{rule}: {detail}" if detail else rule)
