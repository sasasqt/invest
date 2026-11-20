"""Every package carries the root license text and declares the same SPDX license.

PEP 639 forbids ``license-files`` outside a package folder, so each package keeps a
copy of the root ``LICENSE`` for its wheel and source archive (README, License).
"""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LICENSE_EXPRESSION = "AGPL-3.0-or-later"
PACKAGE_DIRS = ("data-pipeline/data-preparation", "data-mining-framework", "strategy-evaluation")


def _project_table(folder: Path) -> dict[str, object]:
    data = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


def test_root_license_is_the_agpl_v3() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE\n")
    assert "Version 3, 19 November 2007" in text


@pytest.mark.parametrize("package_dir", PACKAGE_DIRS)
def test_package_license_copy_matches_root(package_dir: str) -> None:
    assert (ROOT / package_dir / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize("folder", ("", *PACKAGE_DIRS))
def test_pyproject_declares_the_license(folder: str) -> None:
    project = _project_table(ROOT / folder)
    assert project["license"] == LICENSE_EXPRESSION
    assert project["license-files"] == ["LICENSE"]
