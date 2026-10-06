"""Check relative links and heading anchors in the repository's Markdown files.

Usage: python scripts/check_markdown_links.py [ROOT]

External (http, https, mailto) links are not fetched, so the check is offline and
deterministic. Exits non-zero and lists every broken link.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"(`+)(.*?)\1")
EXTERNAL = ("http://", "https://", "mailto:")


def _markdown_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=root, capture_output=True, text=True, check=True
    )
    return [root / line for line in out.stdout.splitlines() if line]


def _lines_outside_code(text: str) -> list[str]:
    lines, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return lines


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # keep link text only
    # Remove formatting markers without discarding underscores inside code spans.
    text = re.sub(r"(`+)(.*?)\1|[*_]", lambda m: m.group(2) if m.group(1) else "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for line in _lines_outside_code(path.read_text(encoding="utf-8")):
        m = HEADING.match(line)
        if not m:
            continue
        base = slug(m.group(2))
        n = counts.get(base, 0)
        counts[base] = n + 1
        found.add(base if n == 0 else f"{base}-{n}")
    return found


def check(root: Path) -> list[str]:
    errors: list[str] = []
    cache: dict[Path, set[str]] = {}
    for md in _markdown_files(root):
        for line in _lines_outside_code(md.read_text(encoding="utf-8")):
            for target in LINK.findall(INLINE_CODE.sub("", line)):
                if target.startswith(EXTERNAL):
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (md.parent / file_part).resolve() if file_part else md
                where = f"{md.relative_to(root)}: {target}"
                if not dest.exists():
                    errors.append(f"{where} -> missing file")
                    continue
                if anchor and dest.suffix == ".md":
                    known = cache.setdefault(dest, anchors(dest))
                    if anchor not in known:
                        errors.append(f"{where} -> missing anchor #{anchor}")
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    errors = check(root)
    for e in errors:
        print(e)
    print(f"{len(errors)} broken link(s)" if errors else "All Markdown links resolve.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
