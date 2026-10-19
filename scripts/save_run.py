"""Save the small, reviewable record of a historical workflow run for committing to Git.

Usage: python scripts/save_run.py OUT_DIR DEST [--snapshot SNAPSHOT_DIR]

Copies reports, metrics, verdicts, resolved configs, figures and bundle/snapshot manifests
from a finished ``scripts/historical_workflow.sh`` output directory into DEST (for example
``runs/yahoo-test/2026-10-08``) and writes a README with the run's provenance. Raw vendor
responses, published bundles and large ledgers are never copied: they are vendor data or
are rebuilt exactly by replaying the snapshot. DEST must not exist, so a record is never
overwritten.

The output must be complete (every file the workflow writes and the README describes) and
must come from committed code: the evaluation and quantile-portfolio manifests need a code
revision and no uncommitted changes to tracked files.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

# Paths relative to the workflow output directory. Nothing else is copied.
RECORD_GLOBS = (
    "data/*/manifest.json",
    "signals/manifest.json",
    "mining/factor.json",
    "mining/diagnostics/*.json",
    "mining/diagnostics/figures/*.png",
    "mining/diagnostics/tables/daily_ic.csv",
    "mining/diagnostics/tables/quantile_returns.csv",
    "mining/diagnostics/tables/quantile_summary.csv",
    "mining/diagnostics/tables/tail_returns.csv",
    "eval/*.json",
    "eval/report.md",
    "eval/figures/*.png",
    "eval/tables/scenarios.csv",
    "quantiles/*.json",
    "quantiles/report.md",
    "quantiles/figures/*.png",
    "quantiles/tables/portfolios.csv",
)
# Every output of a finished historical workflow run; a record missing any of them is refused.
# The benchmark manifest is also required when the evaluation used an external benchmark.
REQUIRED = (
    "data/market/manifest.json",
    "signals/manifest.json",
    "mining/factor.json",
    "mining/diagnostics/config.json",
    "mining/diagnostics/metrics.json",
    "mining/diagnostics/figures/ic.png",
    "mining/diagnostics/figures/quantiles.png",
    "mining/diagnostics/tables/daily_ic.csv",
    "mining/diagnostics/tables/quantile_returns.csv",
    "mining/diagnostics/tables/quantile_summary.csv",
    "mining/diagnostics/tables/tail_returns.csv",
    "eval/config.json",
    "eval/manifest.json",
    "eval/metrics.json",
    "eval/statistics.json",
    "eval/verdict.json",
    "eval/report.md",
    "eval/figures/diagnostics.png",
    "eval/figures/equity_drawdown.png",
    "eval/figures/scenarios.png",
    "eval/tables/scenarios.csv",
    "quantiles/config.json",
    "quantiles/manifest.json",
    "quantiles/quantiles.json",
    "quantiles/report.md",
    "quantiles/figures/quantile_portfolios.png",
    "quantiles/tables/portfolios.csv",
)
# Outputs whose code revision must be recorded and clean.
CODE_MANIFESTS = ("eval/manifest.json", "quantiles/manifest.json")
MAX_FILE_BYTES = 1_000_000


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def record_files(out: Path) -> list[Path]:
    """Relative paths of the files that belong in a run record, checked for completeness,
    provenance and size."""
    if not (out / "eval/manifest.json").is_file():
        raise SystemExit(f"{out}: not a finished workflow output (missing eval/manifest.json)")
    manifest = _load(out / "eval/manifest.json")
    required = list(REQUIRED)
    if manifest.get("external_benchmark"):
        required.append("data/benchmark/manifest.json")
    missing = [rel for rel in required if not (out / rel).is_file()]
    if missing:
        raise SystemExit(f"{out}: not a finished workflow output (missing {', '.join(missing)})")
    for rel in CODE_MANIFESTS:
        code = _load(out / rel)
        if not code.get("code_revision"):
            raise SystemExit(f"{out}: {rel} records no code revision")
        if code.get("code_dirty") is not False:
            raise SystemExit(
                f"{out}: the code behind {rel} had uncommitted changes (or did not record "
                "whether it had); rerun from a clean checkout"
            )
    files = sorted({p.relative_to(out) for pattern in RECORD_GLOBS for p in out.glob(pattern)})
    large = [str(rel) for rel in files if (out / rel).stat().st_size > MAX_FILE_BYTES]
    if large:
        raise SystemExit(f"refusing files over {MAX_FILE_BYTES} bytes: {', '.join(large)}")
    return files


def _readme(out: Path, snapshot: dict[str, Any] | None) -> str:
    manifest = _load(out / "eval/manifest.json")
    verdict = _load(out / "eval/verdict.json")
    market = manifest["market_dataset"]
    lines = [
        f"# Run record: {market['id']}",
        "",
        "Saved by `scripts/save_run.py` from a `scripts/historical_workflow.sh` run. "
        "Test-only Yahoo data is survivorship-biased: read these results as exploratory, "
        "not as alpha evidence. See [eval/report.md](eval/report.md) for the full report "
        "and [quantiles/report.md](quantiles/report.md) for the decile and tail portfolios.",
        "",
        "## Provenance",
        "",
        "| item | value |",
        "|---|---|",
    ]
    if snapshot is not None:
        request = snapshot["request"]
        failures = ", ".join(sorted(snapshot.get("failures", {}))) or "none"
        lines += [
            f"| Snapshot retrieved | {snapshot['retrieved_at']} |",
            f"| Snapshot request | {request['start']} to {request['end']}, "
            f"{len(request['symbols'])} symbols; failed: {failures} |",
        ]
    lines += [
        f"| Code revision | `{manifest.get('code_revision')}` |",
        f"| Market bundle | `{market['sha256']}` |",
    ]
    benchmark = manifest.get("external_benchmark")
    if benchmark:
        lines.append(f"| Benchmark {benchmark['instrument']} | `{benchmark['sha256']}` |")
    lines += [
        f"| Signals | `{manifest['signals']['sha256']}` ({manifest['signals']['id']}) |",
        f"| Factor verdict | `{verdict['factor']['status']}` |",
        f"| Portfolio verdict | `{verdict['portfolio']['status']}` "
        f"(verdict version {verdict.get('verdict_version')}) |",
        "",
        "## Not included",
        "",
        "Raw vendor responses, published bundles and large ledgers are not committed. They "
        "are vendor data or are rebuilt exactly by replaying the raw snapshot, whose files "
        "must match the SHA-256 values in `snapshot/snapshot.json`: "
        "`SNAPSHOT=<dir> uv run scripts/historical_workflow.sh <out>`.",
        "",
    ]
    return "\n".join(lines)


def save_run(out: Path, dest: Path, snapshot_dir: Path | None = None) -> list[Path]:
    """Copy the run record from ``out`` into a new directory ``dest``."""
    files = record_files(out)
    snapshot = None
    if snapshot_dir is not None:
        snapshot_manifest = snapshot_dir / "snapshot.json"
        if not snapshot_manifest.is_file():
            raise SystemExit(f"{snapshot_dir}: no snapshot.json")
        snapshot = _load(snapshot_manifest)
    if dest.exists():
        raise SystemExit(f"{dest}: already exists; run records are never overwritten")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A fresh, uniquely named staging directory: only this call creates it, so only this
    # call removes it. Nothing that already existed is ever deleted. The record is built in
    # a subdirectory so it gets normal permissions rather than mkdtemp's private mode.
    owned = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", suffix=".partial", dir=dest.parent))
    stage = owned / "record"
    stage.mkdir()
    reserved = False
    try:
        for rel in files:
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / rel, stage / rel)
        if snapshot_dir is not None:
            (stage / "snapshot").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snapshot_dir / "snapshot.json", stage / "snapshot/snapshot.json")
        (stage / "README.md").write_text(_readme(out, snapshot))
        # Windows rename already refuses any existing destination. POSIX rename can
        # replace an empty directory, so reserve DEST exclusively on POSIX first.
        try:
            if sys.platform != "win32":
                dest.mkdir()
                reserved = True
            stage.rename(dest)
        except FileExistsError:
            raise SystemExit(f"{dest}: already exists; run records are never overwritten") from None
    except BaseException:
        if reserved and dest.is_dir() and not any(dest.iterdir()):
            dest.rmdir()
        raise
    finally:
        shutil.rmtree(owned, ignore_errors=True)
    return sorted(p.relative_to(dest) for p in dest.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="historical workflow output directory")
    parser.add_argument("dest", type=Path, help="new record directory, e.g. runs/yahoo-test/DATE")
    parser.add_argument("--snapshot", type=Path, help="raw snapshot directory (manifest only)")
    args = parser.parse_args(argv)
    saved = save_run(args.out, args.dest, args.snapshot)
    print(json.dumps({"record": str(args.dest), "files": len(saved)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
