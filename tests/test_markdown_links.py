"""The Markdown link checker used by CI catches broken files and anchors."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

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
    assert mdlinks.slug("snake_case and a__b") == "snake_case-and-a__b"
    assert mdlinks.slug("_emphasis_ word") == "emphasis-word"
    assert mdlinks.slug("__strong__ word") == "strong-word"
    assert mdlinks.slug("_private") == "_private"
    assert mdlinks.slug("public_") == "public_"
    assert mdlinks.slug("trailing__") == "trailing__"
    assert mdlinks.slug("_two words_") == "two-words"


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


def test_literal_underscores_and_colliding_heading_anchors_resolve(tmp_path):
    (tmp_path / "a.md").write_text(
        "## _private\n## public_\n## foo\n## foo\n## foo-1\n## foo\n"
        "[Private](#_private) [Public](#public_) [First](#foo) [Second](#foo-1)\n"
        "[Named](#foo-1-1) [Third](#foo-2)\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert mdlinks.check(tmp_path) == []
    assert mdlinks.anchors(tmp_path / "a.md") == {
        "_private",
        "public_",
        "foo",
        "foo-1",
        "foo-1-1",
        "foo-2",
    }


@pytest.mark.parametrize(
    "example",
    [
        "````markdown\n```\n[example](missing.md)\n````\n",
        "~~~markdown\n```\n[example](missing.md)\n~~~\n",
        "```markdown\n```info\n[example](missing.md)\n```\n",
        "   `````markdown\n````\n[example](missing.md)\n   ``````\n",
    ],
)
def test_only_matching_fences_end_code_examples(tmp_path, example):
    (tmp_path / "a.md").write_text(example + "\n[After](missing-after.md)\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert mdlinks.check(tmp_path) == ["a.md: missing-after.md -> missing file"]
