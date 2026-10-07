"""Run-record safety in scripts/save_run.py: staging, completeness and code provenance."""

import importlib.util
import json
import re
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
