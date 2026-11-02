"""Check a saved snapshot against a trusted manifest without interpreting prices."""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path, PurePosixPath


class SnapshotError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)


def verify(expected_path, snapshot):
    expected_path, snapshot = Path(expected_path), Path(snapshot)
    expected = _json(expected_path)
    request = expected.get("request", {})
    start, end = date.fromisoformat(request["start"]), date.fromisoformat(request["end"])
    if end < start or end >= date(2025, 1, 1):
        raise SnapshotError("Only an already-inspected pre-2025 request is permitted")
    if snapshot.is_symlink():
        raise SnapshotError("Snapshot root must not be a symlink")
    if not snapshot.is_dir():
        return {"status": "blocked", "reason": "matching snapshot directory unavailable"}
    manifest = snapshot / "snapshot.json"
    if manifest.is_symlink():
        raise SnapshotError("Snapshot manifest must not be a symlink")
    if not manifest.is_file():
        return {"status": "blocked", "reason": "snapshot manifest unavailable"}
    actual = _json(manifest)
    if actual != expected:
        raise SnapshotError("Snapshot manifest differs from the recorded request/file identity")
    seen = set()
    total = 0
    missing = []
    root = snapshot.resolve()
    for symbol, entry in expected["files"].items():
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("raw",):
            raise SnapshotError(f"Unsafe raw path for {symbol}")
        if str(relative) in seen:
            raise SnapshotError("Duplicate raw path")
        seen.add(str(relative))
        path = snapshot.joinpath(*relative.parts)
        probe = path
        while probe != snapshot:
            if probe.is_symlink():
                raise SnapshotError(f"Symlink in raw path for {symbol}")
            probe = probe.parent
        if not path.resolve().is_relative_to(root):
            raise SnapshotError(f"Raw path escapes snapshot for {symbol}")
        if not path.is_file():
            missing.append(str(relative))
            continue
        size = path.stat().st_size
        if type(entry["bytes"]) is not int or size != entry["bytes"]:
            raise SnapshotError(f"Wrong byte count for {symbol}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != entry["sha256"]:
            raise SnapshotError(f"Wrong SHA-256 for {symbol}")
        total += size
    return {
        "status": "blocked" if missing else "verified",
        "files": len(seen),
        "verified_bytes": total,
        "missing": missing,
        "request": request,
        "observations_interpreted": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    try:
        result = verify(args.expected, args.snapshot)
    except (SnapshotError, OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "rejected", "reason": str(exc)}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "verified" else 2)
