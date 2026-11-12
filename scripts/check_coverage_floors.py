"""Check test coverage against the floors in ``pyproject.toml``.

Run after the test suite (CI does the same)::

    uv run coverage json -q -o coverage.json
    uv run python scripts/check_coverage_floors.py coverage.json

A file's coverage is coverage.py's ``percent_covered``: lines and branches combined,
because the suite runs with ``--cov-branch``. The floors live in
``[tool.invest.coverage]``: ``total`` for the whole report, ``default`` for a file
without a floor of its own, and ``files`` mapping ``"<package>/<module path>"`` to a
percent. The exit status is 1 when the total or any file is below its floor, or when
a floor names a file the report does not contain (a renamed or deleted module), and
0 otherwise. Files and a total whose coverage has risen a whole point or more above
their floor, and files without a floor of their own, are listed under "can raise" so
the floor can be raised or added; that never fails the check.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module_key(path: str) -> str:
    """Return the part of a report path after its last ``src`` folder, with ``/``.

    ``data-pipeline/data-preparation/src/invest_data/bundle.py`` and the same path with
    Windows separators both give ``invest_data/bundle.py``.
    """
    parts = path.replace("\\", "/").split("/")
    if "src" in parts:
        last = len(parts) - 1 - parts[::-1].index("src")
        parts = parts[last + 1 :]
    return "/".join(parts)


def load_floors(pyproject: Path) -> dict:
    """Read ``[tool.invest.coverage]`` and check its shape."""
    with pyproject.open("rb") as fh:
        table = tomllib.load(fh).get("tool", {}).get("invest", {}).get("coverage")
    if not isinstance(table, dict):
        raise ValueError(f"{pyproject}: no [tool.invest.coverage] table")
    floors = {
        "total": table.get("total"),
        "default": table.get("default"),
        "files": table.get("files", {}),
    }
    numbers = [("total", floors["total"]), ("default", floors["default"])]
    numbers += [(f"files.{k}", v) for k, v in floors["files"].items()]
    for name, value in numbers:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{pyproject}: coverage floor {name} must be a number")
        if not 0 <= value <= 100:
            raise ValueError(f"{pyproject}: coverage floor {name} must be within 0..100")
    return floors


def check(report: dict, floors: dict) -> tuple[list[str], list[str]]:
    """Return (failures, floors that could be raised) for a coverage.py JSON report."""
    failures: list[str] = []
    raisable: list[str] = []
    seen: dict[str, float] = {}
    for path, entry in sorted(report.get("files", {}).items()):
        key = module_key(path)
        if key in seen:
            failures.append(f"{key}: two report files map to this name")
            continue
        percent = float(entry["summary"]["percent_covered"])
        seen[key] = percent
        floor = floors["files"].get(key, floors["default"])
        if percent < floor:
            failures.append(f"{key}: {percent:.2f}% is below its floor {floor}%")
        elif key not in floors["files"]:
            raisable.append(
                f"{key}: {percent:.2f}%, no floor yet, set it to {math.floor(percent)}%"
            )
        elif math.floor(percent) > floor:
            raisable.append(
                f"{key}: {percent:.2f}%, floor {floor}% can rise to {math.floor(percent)}%"
            )
    for key in sorted(set(floors["files"]) - set(seen)):
        failures.append(f"{key}: has a floor but is not in the coverage report")
    total = float(report["totals"]["percent_covered"])
    if total < floors["total"]:
        failures.append(f"total: {total:.2f}% is below its floor {floors['total']}%")
    elif math.floor(total) > floors["total"]:
        raisable.append(
            f"total: {total:.2f}%, floor {floors['total']}% can rise to {math.floor(total)}%"
        )
    return failures, raisable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="coverage.py JSON report")
    parser.add_argument("--pyproject", type=Path, default=ROOT / "pyproject.toml")
    args = parser.parse_args(argv)
    floors = load_floors(args.pyproject)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    failures, raisable = check(report, floors)
    for line in raisable:
        print(f"can raise  {line}")
    for line in failures:
        print(f"FAIL  {line}")
    total = float(report["totals"]["percent_covered"])
    print(f"coverage floors: {len(failures)} failure(s), total {total:.2f}%")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
