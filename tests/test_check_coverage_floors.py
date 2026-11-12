"""The coverage floor check used by CI fails below a floor and on stale floors."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("floors", ROOT / "scripts/check_coverage_floors.py")
assert _spec and _spec.loader
floors_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floors_mod)


def _report(files: dict[str, float], total: float) -> dict:
    return {
        "files": {p: {"summary": {"percent_covered": v}} for p, v in files.items()},
        "totals": {"percent_covered": total},
    }


FLOORS = {"total": 95, "default": 90, "files": {"invest_x/a.py": 88, "invest_x/b.py": 100}}


def test_module_key_strips_up_to_the_last_src_folder_on_both_separators():
    assert floors_mod.module_key("data-pipeline/data-preparation/src/invest_data/bundle.py") == (
        "invest_data/bundle.py"
    )
    assert floors_mod.module_key("strategy-evaluation\\src\\invest_evaluation\\engine.py") == (
        "invest_evaluation/engine.py"
    )
    assert floors_mod.module_key("src/pkg/src/invest_y/sub/c.py") == "invest_y/sub/c.py"
    assert floors_mod.module_key("invest_y/c.py") == "invest_y/c.py"


def test_files_at_or_above_their_floors_pass():
    report = _report({"comp/src/invest_x/a.py": 88.0, "comp/src/invest_x/b.py": 100.0}, 95.0)
    assert floors_mod.check(report, FLOORS) == ([], [])


def test_a_file_below_its_floor_fails():
    report = _report({"comp/src/invest_x/a.py": 87.99, "comp/src/invest_x/b.py": 100.0}, 96.0)
    failures, _ = floors_mod.check(report, FLOORS)
    assert failures == ["invest_x/a.py: 87.99% is below its floor 88%"]


def test_a_file_without_a_floor_at_or_above_the_default_is_listed_for_a_floor():
    report = _report(
        {
            "comp/src/invest_x/a.py": 88.0,
            "comp/src/invest_x/b.py": 100.0,
            "c/src/invest_x/n.py": 93.4,
        },
        95.0,
    )
    assert floors_mod.check(report, FLOORS) == (
        [],
        ["invest_x/n.py: 93.40%, no floor yet, set it to 93%"],
    )


def test_a_total_a_whole_point_above_its_floor_is_listed_as_raisable():
    report = _report({"comp/src/invest_x/a.py": 88.0, "comp/src/invest_x/b.py": 100.0}, 96.0)
    assert floors_mod.check(report, FLOORS) == ([], ["total: 96.00%, floor 95% can rise to 96%"])


def test_a_file_without_a_floor_uses_the_default():
    report = _report(
        {
            "comp/src/invest_x/a.py": 90.0,
            "comp/src/invest_x/b.py": 100.0,
            "c/src/invest_x/new.py": 89.5,
        },
        96.0,
    )
    failures, _ = floors_mod.check(report, FLOORS)
    assert failures == ["invest_x/new.py: 89.50% is below its floor 90%"]


def test_a_floor_for_a_file_missing_from_the_report_fails():
    report = _report({"comp/src/invest_x/a.py": 90.0}, 96.0)
    failures, _ = floors_mod.check(report, FLOORS)
    assert failures == ["invest_x/b.py: has a floor but is not in the coverage report"]


def test_total_below_its_floor_fails():
    report = _report({"comp/src/invest_x/a.py": 90.0, "comp/src/invest_x/b.py": 100.0}, 94.99)
    failures, _ = floors_mod.check(report, FLOORS)
    assert failures == ["total: 94.99% is below its floor 95%"]


def test_two_report_paths_with_the_same_module_name_fail():
    report = _report(
        {"a/src/invest_x/a.py": 90.0, "b/src/invest_x/a.py": 90.0, "c/src/invest_x/b.py": 100.0},
        96.0,
    )
    failures, _ = floors_mod.check(report, FLOORS)
    assert failures == ["invest_x/a.py: two report files map to this name"]


def test_a_whole_point_above_the_floor_is_listed_as_raisable_without_failing():
    report = _report({"comp/src/invest_x/a.py": 89.0, "comp/src/invest_x/b.py": 100.0}, 95.5)
    failures, raisable = floors_mod.check(report, FLOORS)
    assert failures == []
    assert raisable == ["invest_x/a.py: 89.00%, floor 88% can rise to 89%"]
    report = _report({"comp/src/invest_x/a.py": 88.99, "comp/src/invest_x/b.py": 100.0}, 95.5)
    assert floors_mod.check(report, FLOORS) == ([], [])


@pytest.mark.parametrize(
    "table, message",
    [
        ("", "no [tool.invest.coverage] table"),
        ("[tool.invest.coverage]\ntotal = 95\n", "default must be a number"),
        ("[tool.invest.coverage]\ntotal = 95\ndefault = 101\n", "default must be within 0..100"),
        ('[tool.invest.coverage]\ntotal = "95"\ndefault = 90\n', "total must be a number"),
        ("[tool.invest.coverage]\ntotal = true\ndefault = 90\n", "total must be a number"),
        (
            "[tool.invest.coverage]\ntotal = 95\ndefault = 90\n"
            '[tool.invest.coverage.files]\n"x.py" = -1\n',
            "files.x.py must be within 0..100",
        ),
    ],
)
def test_malformed_floor_tables_are_refused(tmp_path, table, message):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(table, encoding="utf-8")
    with pytest.raises(ValueError, match=re.escape(message)):
        floors_mod.load_floors(pyproject)


def test_main_exit_status_and_output(tmp_path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.invest.coverage]\ntotal = 95\ndefault = 90\n"
        '[tool.invest.coverage.files]\n"invest_x/a.py" = 88\n',
        encoding="utf-8",
    )
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps(_report({"c/src/invest_x/a.py": 88.5}, 95.5)), encoding="utf-8")
    assert floors_mod.main([str(report), "--pyproject", str(pyproject)]) == 0
    assert "0 failure(s), total 95.50%" in capsys.readouterr().out
    report.write_text(json.dumps(_report({"c/src/invest_x/a.py": 80.0}, 95.5)), encoding="utf-8")
    assert floors_mod.main([str(report), "--pyproject", str(pyproject)]) == 1
    assert "FAIL  invest_x/a.py: 80.00% is below its floor 88%" in capsys.readouterr().out


def test_the_repository_floor_table_is_well_formed():
    floors = floors_mod.load_floors(ROOT / "pyproject.toml")
    assert floors["files"], "the repository lists per-file floors"
    for key in floors["files"]:
        assert key.startswith("invest_") and key.endswith(".py"), key
        assert key.partition("/")[2], key


def test_floors_at_the_ends_of_the_range_are_accepted(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.invest.coverage]\ntotal = 0\ndefault = 100\n", encoding="utf-8")
    assert floors_mod.load_floors(pyproject) == {"total": 0, "default": 100, "files": {}}


def test_module_key_keeps_a_src_folder_inside_a_package():
    # Round 1 finding: a subpackage named src must not cut the key short.
    assert floors_mod.module_key("data-mining-framework/src/invest_mining/src/helpers.py") == (
        "invest_mining/src/helpers.py"
    )


def test_module_key_starts_at_the_outermost_package_and_keeps_top_level_modules():
    assert floors_mod.module_key("c/src/invest_a/src/invest_b/m.py") == "invest_a/src/invest_b/m.py"
    assert floors_mod.module_key("c/src/invest_tool.py") == "invest_tool.py"


def test_module_key_maps_installed_wheel_paths():
    # Round 1 finding: a report taken against installed wheels uses site-packages paths.
    assert floors_mod.module_key("venv/lib/python3.11/site-packages/invest_data/bundle.py") == (
        "invest_data/bundle.py"
    )
    assert floors_mod.module_key("C:\\venv\\Lib\\site-packages\\invest_data\\bundle.py") == (
        "invest_data/bundle.py"
    )


def test_a_files_entry_that_is_not_a_table_is_refused(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.invest.coverage]\ntotal = 95\ndefault = 90\nfiles = 90\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match=re.escape("coverage floor files must be a table")):
        floors_mod.load_floors(pyproject)


def test_main_works_without_a_module_docstring(tmp_path, monkeypatch):
    # Round 1 finding: python -OO strips docstrings.
    monkeypatch.setattr(floors_mod, "__doc__", None)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.invest.coverage]\ntotal = 95\ndefault = 90\n", encoding="utf-8")
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps(_report({"c/src/invest_x/a.py": 91.0}, 95.5)), encoding="utf-8")
    assert floors_mod.main([str(report), "--pyproject", str(pyproject)]) == 0
