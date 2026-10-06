"""The Markdown link checker used by CI catches broken files and anchors."""

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mdlinks", ROOT / "scripts/check_markdown_links.py")
assert _spec and _spec.loader
mdlinks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mdlinks)


def test_slug_matches_github_anchors():
    assert mdlinks.slug("M0 — Contracts and initial scope") == "m0--contracts-and-initial-scope"
    assert mdlinks.slug("Updating the backlog and README") == "updating-the-backlog-and-readme"
    assert mdlinks.slug("`invest-eval` [run](x.md)") == "invest-eval-run"
    assert mdlinks.slug("`invest_eval` *run*") == "invest_eval-run"


def test_check_reports_missing_files_and_anchors(tmp_path):
    (tmp_path / "a.md").write_text(
        "# Title\n\n## Part\n\n[ok](b.md#section) [self](#part) [web](https://x.invalid)\n"
        "[gone](missing.md) [bad](b.md#nope)\n\n```\n[ignored](in-code.md)\n```\n"
    )
    (tmp_path / "b.md").write_text("# Section\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert mdlinks.check(tmp_path) == [
        "a.md: missing.md -> missing file",
        "a.md: b.md#nope -> missing anchor #nope",
    ]


def test_repository_links_resolve():
    assert mdlinks.check(ROOT) == []


def test_inline_code_is_preserved_in_heading_anchors_but_not_checked_for_links(tmp_path):
    (tmp_path / "a.md").write_text(
        "# Title\n\n## `invest-eval` run\n\n"
        "[CLI](#invest-eval-run)\n"
        "`[example](missing.md)` and ``[example](other-missing.md)``\n"
        "\n## `invest-eval` run\n\n[Again](#invest-eval-run-1)\n"
        "\n## `invest_eval` run\n\n[Python](#invest_eval-run)\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert mdlinks.check(tmp_path) == []
    assert {"invest-eval-run", "invest-eval-run-1", "invest_eval-run"} <= mdlinks.anchors(
        tmp_path / "a.md"
    )
