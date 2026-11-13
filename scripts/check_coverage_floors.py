"""Check test coverage against the floors in ``pyproject.toml``.

Run after the test suite (CI does the same)::

    uv run coverage json -q -o coverage.json
    uv run python scripts/check_coverage_floors.py coverage.json

A file's coverage is coverage.py's ``percent_covered``: lines and branches combined,
because the suite runs with ``--cov-branch``. The floors live in
``[tool.invest.coverage]``: ``total`` for the whole report, ``default`` for a file
without a floor of its own, and ``files`` mapping ``"<package>/<module path>"`` to a
percent. The exit status is 1 when the total or any file is below its floor, when two
report paths map to the same key, or when a floor names a file the report does not
contain (a renamed or deleted module: rename or remove its floor in the same change);
2 when the floor table or the report cannot be read, or the report has no branch data
(pytest ran without ``--cov-branch``); and 0 otherwise. Files and a total whose
coverage has risen a whole point or more above their floor, and files without a floor
of their own, are listed under "can raise" so the floor can be raised or added; that
never fails the check.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tomllib
from collections.abc import Collection
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[1]


class Floors(TypedDict):
    """The ``[tool.invest.coverage]`` table, every value a percent within 0..100."""

    total: float
    default: float
    files: dict[str, float]


def module_key(path: str, packages: Collection[str] = ()) -> str:
    """Return a report path from its package folder on, with ``/``.

    With ``packages`` (the top-level package names the floors use), the key starts at
    the innermost folder that is one of them, so an outer folder never takes over:
    ``/home/u/src/invest_venv/lib/python3.11/site-packages/invest_data/bundle.py``
    gives ``invest_data/bundle.py``, and a folder named ``src`` inside a package is
    kept. Otherwise the key starts after the last ``src`` or ``site-packages`` folder
    (in any letter case), so ``data-pipeline/data-preparation/src/invest_data/bundle.py``,
    its Windows form and ``venv/Lib/site-packages/invest_data/bundle.py`` all give
    ``invest_data/bundle.py``. A path with neither is returned whole.
    """
    parts = path.replace("\\", "/").split("/")
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] in packages:
            return "/".join(parts[i:])
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].lower() in ("src", "site-packages"):
            return "/".join(parts[i + 1 :])
    return "/".join(parts)


def load_floors(pyproject: Path) -> Floors:
    """Read ``[tool.invest.coverage]`` and check its shape."""
    with pyproject.open("rb") as fh:
        table: object = tomllib.load(fh)
    for name in ("tool", "invest", "coverage"):  # any level may be a non-table value
        table = table.get(name) if isinstance(table, dict) else None
    if not isinstance(table, dict):
        raise ValueError(f"{pyproject}: no [tool.invest.coverage] table")
    if not isinstance(table.get("files", {}), dict):
        raise ValueError(f"{pyproject}: coverage floor files must be a table")

    def number(name: str, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{pyproject}: coverage floor {name} must be a number")
        if not 0 <= value <= 100:
            raise ValueError(f"{pyproject}: coverage floor {name} must be within 0..100")
        return value

    return Floors(
        total=number("total", table.get("total")),
        default=number("default", table.get("default")),
        files={k: number(f"files.{k}", v) for k, v in table.get("files", {}).items()},
    )


def percent_covered(summary: dict[str, Any], where: str) -> float:
    """Return a report's ``percent_covered``, refusing anything but a number in 0..100."""
    value = summary["percent_covered"]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{where}: percent_covered {value!r} is not a number")
    if not 0 <= value <= 100:  # also refuses NaN and infinity
        raise ValueError(f"{where}: percent_covered {value!r} is not within 0..100")
    return float(value)


def shown(percent: float, floor: float) -> str:
    """Two decimals, or every digit when rounding to two would cross ``floor`` or a whole
    percent, so 94.9999 below a floor of 95 is shown as ``94.9999``, never ``95.00``."""
    text = f"{percent:.2f}"
    rounded = float(text)
    if (rounded < floor) == (percent < floor) and math.floor(rounded) == math.floor(percent):
        return text
    return repr(percent)


def check(report: dict[str, Any], floors: Floors) -> tuple[list[str], list[str]]:
    """Return (failures, floors that could be raised) for a coverage.py JSON report."""
    failures: list[str] = []
    raisable: list[str] = []
    packages = {key.split("/", 1)[0] for key in floors["files"]}
    seen: dict[str, str] = {}
    for path, entry in sorted(report.get("files", {}).items()):
        key = module_key(path, packages)
        percent = percent_covered(entry["summary"], path)
        if key in seen:
            failures.append(f"{key}: two report files map to this name ({seen[key]}, {path})")
            continue
        seen[key] = path
        floor = floors["files"].get(key, floors["default"])
        text, whole = shown(percent, floor), math.floor(percent)
        if percent < floor:
            failures.append(f"{key}: {text}% is below its floor {floor}%")
        elif key not in floors["files"]:
            # Never suggest a floor below the default the file already has to meet.
            suggest = max(whole, floors["default"])
            raisable.append(f"{key}: {text}%, no floor yet, set it to {suggest}%")
        elif whole > floor:
            raisable.append(f"{key}: {text}%, floor {floor}% can rise to {whole}%")
    for key in sorted(set(floors["files"]) - set(seen)):
        failures.append(f"{key}: has a floor but is not in the coverage report")
    total = percent_covered(report["totals"], "totals")
    floor, text, whole = floors["total"], shown(total, floors["total"]), math.floor(total)
    if total < floor:
        failures.append(f"total: {text}% is below its floor {floor}%")
    elif whole > floor:
        raisable.append(f"total: {text}%, floor {floor}% can rise to {whole}%")
    return failures, raisable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check test coverage against the floors in pyproject.toml."
    )
    parser.add_argument("report", type=Path, help="coverage.py JSON report")
    parser.add_argument("--pyproject", type=Path, default=ROOT / "pyproject.toml")
    args = parser.parse_args(argv)
    try:
        floors = load_floors(args.pyproject)
    except (OSError, ValueError) as exc:  # tomllib.TOMLDecodeError is a ValueError
        print(f"ERROR  {exc}")
        return 2
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        meta = report.get("meta")
        if not (isinstance(meta, dict) and meta.get("branch_coverage") is True):
            # The floors are lines and branches combined; a line-only report reads higher.
            print(f"ERROR  {args.report}: no branch data; run pytest with --cov-branch")
            return 2
        failures, raisable = check(report, floors)
        total = percent_covered(report["totals"], "totals")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"ERROR  {args.report}: not a readable coverage.py JSON report ({exc!r})")
        return 2
    for line in raisable:
        print(f"can raise  {line}")
    for line in failures:
        print(f"FAIL  {line}")
    print(f"coverage floors: {len(failures)} failure(s), total {shown(total, floors['total'])}%")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
