"""Check a saved snapshot against a trusted manifest without interpreting prices."""

import argparse
import hashlib
import json
import re
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
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except RecursionError:
        raise SnapshotError(f"JSON nested too deeply: {path.name}") from None


def _entry(symbol, entry):
    """The safe relative raw path of one manifest entry; reject a malformed entry."""
    # An entry that could never verify (a negative size, a digest that is not 64
    # lower-case hex digits, the raw folder itself) is malformed, not "blocked".
    if (
        not isinstance(entry, dict)
        or not isinstance(entry.get("path"), str)
        or type(entry.get("bytes")) is not int
        or entry["bytes"] < 0
        or not isinstance(entry.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    ):
        raise SnapshotError(f"Malformed manifest entry for {symbol}")
    relative = PurePosixPath(entry["path"])
    # A backslash or colon makes a Windows path rooted, drive-relative or a stream.
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[:1] != ("raw",)
        or len(relative.parts) < 2
        or any("\\" in part or ":" in part or "\0" in part for part in relative.parts)
        or not all(_name_fits(part) for part in relative.parts)
    ):
        raise SnapshotError(f"Unsafe raw path for {symbol}")
    return relative, entry


def _name_fits(part):
    """A name a file can have on Linux: valid UTF-8 (no lone surrogate), at most 255
    bytes. Any other name could never verify, so it is malformed, not "blocked"."""
    try:
        return len(part.encode("utf-8")) <= 255
    except UnicodeEncodeError:
        return False


def verify(expected_path, snapshot):
    expected_path, snapshot = Path(expected_path), Path(snapshot)
    expected = _json(expected_path)
    if not isinstance(expected, dict) or not isinstance(expected.get("files"), dict):
        raise SnapshotError("Manifest must be an object with a files object")
    if not expected["files"]:
        raise SnapshotError("Manifest lists no raw files")
    request = expected.get("request")
    if not isinstance(request, dict) or not all(
        isinstance(request.get(key), str) for key in ("start", "end")
    ):
        raise SnapshotError("Manifest request must name its start and end dates")
    start, end = date.fromisoformat(request["start"]), date.fromisoformat(request["end"])
    if end < start or end >= date(2025, 1, 1):
        raise SnapshotError("Only an already-inspected pre-2025 request is permitted")
    # Check every entry before looking at the snapshot: a malformed or unsafe manifest
    # is rejected (W3), never reported as blocked because its snapshot is missing.
    entries = {symbol: _entry(symbol, entry) for symbol, entry in expected["files"].items()}
    paths = {str(relative) for relative, _ in entries.values()}
    if len(paths) != len(entries):
        raise SnapshotError("Duplicate raw path")
    # A raw path that is also a folder of another raw path can never be a regular
    # file while the other exists, so such a manifest could never verify (W3).
    for relative, _ in entries.values():
        if any(str(parent) in paths for parent in relative.parents):
            raise SnapshotError("Raw path is a folder of another raw path")
    if snapshot.is_symlink():
        raise SnapshotError("Snapshot root must not be a symlink")
    if not snapshot.is_dir():
        if snapshot.exists():
            raise SnapshotError("Snapshot root is not a directory")
        return {"status": "blocked", "reason": "matching snapshot directory unavailable"}
    manifest = snapshot / "snapshot.json"
    if manifest.is_symlink():
        raise SnapshotError("Snapshot manifest must not be a symlink")
    if not manifest.is_file():
        if manifest.exists():
            raise SnapshotError("Snapshot manifest is not a regular file")
        return {"status": "blocked", "reason": "snapshot manifest unavailable"}
    actual = _json(manifest)
    if actual != expected:
        raise SnapshotError("Snapshot manifest differs from the recorded request/file identity")
    total = 0
    missing = []
    root = snapshot.resolve()
    for symbol, (relative, entry) in entries.items():
        path = snapshot.joinpath(*relative.parts)
        probe = path
        while probe != snapshot:
            if probe.is_symlink():
                raise SnapshotError(f"Symlink in raw path for {symbol}")
            probe = probe.parent
        if not path.resolve().is_relative_to(root):
            raise SnapshotError(f"Raw path escapes snapshot for {symbol}")
        if not path.is_file():
            if path.exists():
                raise SnapshotError(f"Raw path is not a regular file for {symbol}")
            missing.append(str(relative))
            continue
        size = path.stat().st_size
        if size != entry["bytes"]:
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
        "files": len(entries),
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
