"""Run-record safety in scripts/save_run.py: staging, completeness, provenance and size."""

import gzip
import hashlib
import importlib.util
import json
import random
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("save_run", ROOT / "scripts/save_run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


save_run = _module()


def _output(tmp_path: Path, **manifest: object) -> Path:
    """A minimal finished workflow output holding every required file."""
    out = tmp_path / "out"
    for rel in [*save_run.REQUIRED, "data/benchmark/manifest.json"]:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text("{}")
    eval_manifest = {
        "market_dataset": {"id": "m", "sha256": "a"},
        "signals": {"id": "s", "sha256": "b"},
        "external_benchmark": {"instrument": "SPY", "sha256": "c"},
        "code_revision": "1" * 40,
        "code_dirty": False,
        **manifest,
    }
    (out / "eval/manifest.json").write_text(json.dumps(eval_manifest))
    (out / "quantiles/manifest.json").write_text(json.dumps(eval_manifest))
    verdict = {"factor": {"status": "not_confirmed"}, "portfolio": {"status": "inconclusive"}}
    (out / "eval/verdict.json").write_text(json.dumps({**verdict, "verdict_version": 2}))
    return out


def test_saves_a_complete_record(tmp_path):
    out = _output(tmp_path)
    saved = {str(p) for p in save_run.save_run(out, tmp_path / "runs" / "day")}
    assert saved == {*save_run.REQUIRED, "data/benchmark/manifest.json", "README.md"}
    assert [p.name for p in (tmp_path / "runs").iterdir()] == ["day"]  # no staging left


def _decile_table(path: Path, days: int) -> bytes:
    """A daily ten-decile table like `invest-mine evaluate` writes, with `days` rows."""
    rng = random.Random(1)
    lines = ["date," + ",".join(f"q{k}" for k in range(1, 11))]
    for day in range(days):
        session = (date(2000, 1, 3) + timedelta(days=day)).isoformat()
        lines.append(session + "," + ",".join(repr(rng.gauss(0.0, 0.01)) for _ in range(10)))
    data = ("\n".join(lines) + "\n").encode("utf-8")
    path.write_bytes(data)
    return data


def test_compresses_an_oversize_table_and_records_how_to_recover_it(tmp_path):
    out = _output(tmp_path)
    rel = "mining/diagnostics/tables/quantile_returns.csv"
    original = _decile_table(out / rel, days=6000)  # about 24 years of sessions
    assert len(original) > save_run.MAX_FILE_BYTES
    dest = tmp_path / "runs" / "day"
    saved = {p.as_posix() for p in save_run.save_run(out, dest)}
    expected = {*save_run.REQUIRED, "data/benchmark/manifest.json", "README.md"}
    assert saved == (expected - {rel}) | {f"{rel}.gz"}
    stored = (dest / f"{rel}.gz").read_bytes()
    assert len(stored) <= save_run.MAX_FILE_BYTES
    assert gzip.decompress(stored) == original  # the figure's input is recovered exactly
    readme = (dest / "README.md").read_text()
    digest = hashlib.sha256(original).hexdigest()
    assert f"| `{rel}` | {len(original)} | `{digest}` |" in readme
    assert "python -m gzip -d FILE.gz" in readme
    assert b"\r" not in (dest / "README.md").read_bytes()  # committed text keeps LF endings
    # The documented recovery command recovers the file next to the stored one.
    subprocess.run([sys.executable, "-m", "gzip", "-d", str(dest / f"{rel}.gz")], check=True)
    recovered = (dest / rel).read_bytes()
    assert len(recovered) == len(original) and hashlib.sha256(recovered).hexdigest() == digest
    # Same input, same bytes on every run with the same zlib build: no timestamp or name in
    # the gzip header.
    save_run.save_run(out, tmp_path / "runs" / "again")
    assert (tmp_path / "runs" / "again" / f"{rel}.gz").read_bytes() == stored


def test_small_tables_are_stored_as_they_are(tmp_path):
    out = _output(tmp_path)
    rel = "mining/diagnostics/tables/quantile_returns.csv"
    original = _decile_table(out / rel, days=3800)  # the 15-year replay's size, under 1 MB
    assert len(original) <= save_run.MAX_FILE_BYTES
    dest = tmp_path / "runs" / "day"
    save_run.save_run(out, dest)
    assert (dest / rel).read_bytes() == original and not (dest / f"{rel}.gz").exists()
    assert "Compressed files" not in (dest / "README.md").read_text()


def test_refuses_a_file_still_over_the_limit_when_compressed(tmp_path):
    out = _output(tmp_path)
    rel = "eval/figures/scenarios.png"
    (out / rel).write_bytes(random.Random(2).randbytes(save_run.MAX_FILE_BYTES + 1))
    with pytest.raises(SystemExit, match=re.escape(f"even compressed: {rel}")):
        save_run.save_run(out, tmp_path / "runs" / "day")
    assert not (tmp_path / "runs").exists()  # refused before anything was staged


@pytest.fixture
def windows_rename(monkeypatch):
    """Exercise Windows' refusal to rename onto an existing target on any CI host."""
    rename = Path.rename
    monkeypatch.setattr(save_run, "sys", SimpleNamespace(platform="win32"))

    def rename_without_replacement(self, target):
        if Path(target).exists():
            raise FileExistsError(f"{target}: Windows rename refuses an existing destination")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", rename_without_replacement)


def test_saves_a_complete_record_with_windows_rename_semantics(tmp_path, windows_rename):
    out = _output(tmp_path)
    dest = tmp_path / "runs" / "day"
    saved = {str(p) for p in save_run.save_run(out, dest)}
    assert saved == {*save_run.REQUIRED, "data/benchmark/manifest.json", "README.md"}
    assert (dest / "eval/manifest.json").read_bytes() == (out / "eval/manifest.json").read_bytes()
    assert [p.name for p in dest.parent.iterdir()] == ["day"]


@pytest.mark.parametrize("nonempty", [False, True])
def test_windows_refuses_a_destination_created_while_saving(
    tmp_path, monkeypatch, windows_rename, nonempty
):
    out = _output(tmp_path)
    dest = tmp_path / "runs" / "day"
    readme = save_run._readme

    def racing_readme(*args: object) -> str:
        dest.mkdir()
        if nonempty:
            (dest / "notes.txt").write_text("mine")
        return readme(*args)

    monkeypatch.setattr(save_run, "_readme", racing_readme)
    with pytest.raises(SystemExit, match="never overwritten"):
        save_run.save_run(out, dest)
    assert sorted(p.name for p in dest.iterdir()) == (["notes.txt"] if nonempty else [])
    if nonempty:
        assert (dest / "notes.txt").read_text() == "mine"
    assert [p.name for p in dest.parent.iterdir()] == ["day"]


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_failed_publication_removes_only_its_own_directories(tmp_path, monkeypatch, platform):
    out = _output(tmp_path)
    dest = tmp_path / "runs" / "day"
    other = dest.parent / ".day.other.partial"
    other.mkdir(parents=True)
    (other / "notes.txt").write_text("mine")
    monkeypatch.setattr(save_run, "sys", SimpleNamespace(platform=platform))

    def fail(*args: object) -> None:
        raise OSError("publication failed")

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OSError, match="publication failed"):
        save_run.save_run(out, dest)
    assert [p.name for p in dest.parent.iterdir()] == [".day.other.partial"]
    assert (other / "notes.txt").read_text() == "mine"


def test_never_deletes_an_existing_directory_named_like_staging(tmp_path):
    out = _output(tmp_path)
    runs = tmp_path / "runs"
    victim = runs / ".day.partial"
    victim.mkdir(parents=True)
    (victim / "notes.txt").write_text("mine")
    save_run.save_run(out, runs / "day")
    assert (victim / "notes.txt").read_text() == "mine"


def test_failed_save_removes_only_its_own_staging(tmp_path, monkeypatch):
    out = _output(tmp_path)
    runs = tmp_path / "runs"
    other = runs / ".day.other.partial"  # for example a concurrent save's staging
    other.mkdir(parents=True)

    def fail(*_: object) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(save_run, "_readme", fail)
    with pytest.raises(RuntimeError, match="boom"):
        save_run.save_run(out, runs / "day")
    assert sorted(p.name for p in runs.iterdir()) == [".day.other.partial"]


def test_refuses_a_destination_created_while_saving(tmp_path, monkeypatch):
    out = _output(tmp_path)
    dest = tmp_path / "runs" / "day"
    readme = save_run._readme

    def racing_readme(*args: object) -> str:
        dest.mkdir()  # an empty directory appears after the existence check
        return readme(*args)

    monkeypatch.setattr(save_run, "_readme", racing_readme)
    with pytest.raises(SystemExit, match="never overwritten"):
        save_run.save_run(out, dest)
    assert dest.is_dir() and not any(dest.iterdir())  # left untouched, not filled
    assert [p.name for p in dest.parent.iterdir()] == ["day"]


@pytest.mark.parametrize(
    "missing", ["eval/report.md", "eval/metrics.json", "eval/figures/scenarios.png"]
)
def test_refuses_an_incomplete_output(tmp_path, missing):
    out = _output(tmp_path)
    (out / missing).unlink()
    with pytest.raises(SystemExit, match=re.escape(f"missing {missing}")):
        save_run.save_run(out, tmp_path / "runs" / "day")
    assert not (tmp_path / "runs" / "day").exists()


def test_requires_the_benchmark_manifest_only_when_a_benchmark_was_used(tmp_path):
    out = _output(tmp_path)
    (out / "data/benchmark/manifest.json").unlink()
    with pytest.raises(SystemExit, match=re.escape("missing data/benchmark/manifest.json")):
        save_run.save_run(out, tmp_path / "runs" / "a")
    out = _output(tmp_path, external_benchmark=None)
    (out / "data/benchmark/manifest.json").unlink()
    assert save_run.save_run(out, tmp_path / "runs" / "b")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"code_revision": None}, "no code revision"),
        ({"code_dirty": True}, "uncommitted changes"),
        ({"code_dirty": None}, "uncommitted changes"),
    ],
)
def test_refuses_runs_without_committed_code(tmp_path, fields, reason):
    out = _output(tmp_path, **fields)
    with pytest.raises(SystemExit, match=reason):
        save_run.save_run(out, tmp_path / "runs" / "day")
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def test_refuses_quantile_portfolios_from_uncommitted_code(tmp_path):
    out = _output(tmp_path)
    manifest = json.loads((out / "quantiles/manifest.json").read_text())
    (out / "quantiles/manifest.json").write_text(json.dumps({**manifest, "code_dirty": True}))
    with pytest.raises(SystemExit, match=r"quantiles/manifest\.json had uncommitted"):
        save_run.save_run(out, tmp_path / "runs" / "day")


def test_record_directory_gets_normal_permissions(tmp_path):
    import os

    umask = os.umask(0o022)
    try:
        save_run.save_run(_output(tmp_path), tmp_path / "runs" / "day")
    finally:
        os.umask(umask)
    assert (tmp_path / "runs" / "day").stat().st_mode & 0o777 == 0o755
