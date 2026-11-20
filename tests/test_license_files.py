"""Every package carries the unmodified AGPL text and declares the same SPDX license.

PEP 639 forbids ``license-files`` outside a package folder, so each workspace member
keeps a copy of the root ``LICENSE`` for its wheel and source archive (README, License).
Hatchling does not fail when a listed license file is missing, so these tests are the
only guard against a missing or drifting copy.
"""

import hashlib
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LICENSE_EXPRESSION = "AGPL-3.0-or-later"
# sha256 of https://www.gnu.org/licenses/agpl-3.0.txt (LF line endings), fetched 2026-11-20.
AGPL_3_SHA256 = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"
# hatchling 1.27 is the first release whose default core metadata (2.4) writes
# License-Expression and License-File; 1.26 writes them only when asked to.
HATCHLING_FLOOR = "hatchling>=1.27"


def _pyproject(folder: Path) -> dict[str, object]:
    return tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))


def _workspace_members() -> list[str]:
    tool = _pyproject(ROOT)["tool"]
    assert isinstance(tool, dict)
    members = tool["uv"]["workspace"]["members"]
    assert isinstance(members, list) and members
    assert all(isinstance(member, str) for member in members)
    return members


MEMBERS = _workspace_members()


def _project_table(folder: Path) -> dict[str, object]:
    project = _pyproject(folder)["project"]
    assert isinstance(project, dict)
    return project


def test_root_license_is_the_unmodified_agpl_v3() -> None:
    # read_text normalizes CRLF, so a Windows checkout with autocrlf passes too.
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == AGPL_3_SHA256


@pytest.mark.parametrize("member", MEMBERS)
def test_member_license_copy_matches_root(member: str) -> None:
    assert (ROOT / member / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize("folder", [".", *MEMBERS])
def test_pyproject_declares_the_license(folder: str) -> None:
    project = _project_table(ROOT / folder)
    assert project["license"] == LICENSE_EXPRESSION
    assert project["license-files"] == ["LICENSE"]


@pytest.mark.parametrize("member", MEMBERS)
def test_member_build_backend_supports_license_expressions(member: str) -> None:
    build_system = _pyproject(ROOT / member)["build-system"]
    assert isinstance(build_system, dict)
    assert build_system["requires"] == [HATCHLING_FLOOR]
