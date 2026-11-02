"""Copy untrusted container output into a bounded, link-free host snapshot.

Linux/POSIX descriptor APIs are required. Unsupported hosts fail closed; this is
not a portable replacement for the container's separate execution boundary.
"""

import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

SUMMARY_NAMES = ("boundary.json", "environment.json", "benchmark-summary.json")
SUMMARY_MAX_BYTES = 64 * 1024


class RejectedOutput(ValueError):
    """The untrusted result tree cannot be collected safely."""


@dataclass(frozen=True)
class CollectionLimits:
    file_bytes: int = 16 * 1024 * 1024
    total_bytes: int = 128 * 1024 * 1024
    entries: int = 4096
    depth: int = 32


DEFAULT_LIMITS = CollectionLimits()


@contextmanager
def directory_fd(path, parent=None):
    if not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise RejectedOutput("descriptor-based collection unavailable")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError as exc:
        raise RejectedOutput("missing, linked or unreadable output directory") from exc
    try:
        yield fd
    finally:
        os.close(fd)


def regular_file(info, device, maximum):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != device:
        raise RejectedOutput("linked, special or cross-device output entry")
    if info.st_size > maximum:
        raise RejectedOutput("output file size limit exceeded")


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_summaries(snapshot):
    """Read only the private host snapshot, never the original /work tree."""
    summaries = {}
    with directory_fd(snapshot) as root:
        device = os.fstat(root).st_dev
        for name in SUMMARY_NAMES:
            try:
                info = os.stat(name, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                continue
            regular_file(info, device, SUMMARY_MAX_BYTES)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
            try:
                opened = os.fstat(fd)
                regular_file(opened, device, SUMMARY_MAX_BYTES)
                if identity(info) != identity(opened):
                    raise RejectedOutput("summary changed during collection")
                payload = bytearray()
                while chunk := os.read(fd, min(65536, SUMMARY_MAX_BYTES + 1 - len(payload))):
                    payload.extend(chunk)
                    if len(payload) > SUMMARY_MAX_BYTES:
                        raise RejectedOutput("summary size limit exceeded")
                if identity(opened) != identity(os.fstat(fd)):
                    raise RejectedOutput("summary changed during collection")
            finally:
                os.close(fd)
            try:
                value = json.loads(payload)
                if not isinstance(value, dict):
                    raise ValueError("summary must be an object")
                pending, nodes = [(value, 0)], 0
                while pending:
                    item, depth = pending.pop()
                    nodes += 1
                    if depth > 32 or nodes > 4096:
                        raise ValueError("summary structure limit exceeded")
                    if isinstance(item, dict):
                        pending.extend((child, depth + 1) for child in item.values())
                    elif isinstance(item, list):
                        pending.extend((child, depth + 1) for child in item)
                # Also reject non-finite JSON constants, and ensure log output
                # escapes newlines instead of interpreting workflow commands.
                json.dumps(value, ensure_ascii=True, allow_nan=False)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise RejectedOutput("invalid JSON summary") from exc
            summaries[name] = value
    return summaries


def collect_results(work, destination, limits=DEFAULT_LIMITS):
    """Reject unsafe output atomically; return data only from the safe snapshot.

    Call after Docker has stopped every container process. All source traversal
    remains relative to open no-follow directory descriptors, including the
    results root; no preserved links are passed on to an artifact uploader.
    """
    if any(value <= 0 for value in asdict(limits).values()):
        raise ValueError("collection limits must be positive")
    work, destination = Path(work), Path(destination)
    if Path(os.path.abspath(destination)).is_relative_to(Path(os.path.abspath(work))) or (
        destination.resolve().is_relative_to(work.resolve())
    ):
        raise ValueError("collection destination must be outside the writable container mount")
    if destination.exists() or destination.is_symlink():
        raise ValueError("collection destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    snapshot = Path(tempfile.mkdtemp(prefix=".collect-", dir=destination.parent))
    records, byte_count, entry_count = [], 0, 0

    def walk(root, target, prefix, depth, device):
        nonlocal byte_count, entry_count
        if depth > limits.depth:
            raise RejectedOutput("output directory depth limit exceeded")
        with os.scandir(root) as children:
            for entry in children:
                name = entry.name
                if any(character in name for character in '\\:*?"<>|') or any(
                    ord(character) < 32 or ord(character) == 127 for character in name
                ):
                    raise RejectedOutput("unsafe artifact filename")
                entry_count += 1
                if entry_count > limits.entries:
                    raise RejectedOutput("output entry count limit exceeded")
                info = os.stat(name, dir_fd=root, follow_symlinks=False)
                relative = prefix / name
                if stat.S_ISDIR(info.st_mode):
                    if info.st_dev != device:
                        raise RejectedOutput("cross-device output directory")
                    with directory_fd(name, root) as child:
                        opened = os.fstat(child)
                        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                            raise RejectedOutput("output directory changed during collection")
                        folder = target / name
                        folder.mkdir(mode=0o700)
                        walk(child, folder, relative, depth + 1, device)
                    continue
                regular_file(info, device, limits.file_bytes)
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
                try:
                    opened = os.fstat(fd)
                    regular_file(opened, device, limits.file_bytes)
                    if identity(info) != identity(opened):
                        raise RejectedOutput("output file changed during collection")
                    digest, copied = hashlib.sha256(), 0
                    with (target / name).open("xb") as output:
                        while chunk := os.read(fd, 65536):
                            copied += len(chunk)
                            byte_count += len(chunk)
                            if copied > limits.file_bytes or byte_count > limits.total_bytes:
                                raise RejectedOutput("output byte limit exceeded")
                            output.write(chunk)
                            digest.update(chunk)
                    if identity(opened) != identity(os.fstat(fd)):
                        raise RejectedOutput("output file changed during collection")
                    records.append(
                        {"path": relative.as_posix(), "bytes": copied, "sha256": digest.hexdigest()}
                    )
                finally:
                    os.close(fd)

    try:
        with directory_fd(work) as parent, directory_fd("results", parent) as root:
            walk(root, snapshot, Path(), 0, os.fstat(root).st_dev)
        summaries = read_summaries(snapshot)
        snapshot.rename(destination)
    except (OSError, RejectedOutput) as exc:
        shutil.rmtree(snapshot)
        if isinstance(exc, RejectedOutput):
            raise
        raise RejectedOutput("unreadable or changing output entry") from exc
    except BaseException:
        shutil.rmtree(snapshot)
        raise
    return {
        "status": "collected",
        "limits": asdict(limits),
        "entries": entry_count,
        "bytes": byte_count,
        "files": sorted(records, key=lambda row: row["path"]),
        "summaries": summaries,
    }


def collect_workload(work, results, limits=DEFAULT_LIMITS):
    """The runner and Docker acceptance harness share this exact host sink."""
    results = Path(results)
    try:
        report = collect_results(work, results / "workload", limits)
    except RejectedOutput as exc:
        report = {"status": "rejected", "reason": str(exc), "limits": asdict(limits)}
    (results / "collection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("AUDIT_COLLECTION " + json.dumps({"status": report["status"]}), flush=True)
    for name, value in report.get("summaries", {}).items():
        print("AUDIT_EVIDENCE " + name + " " + json.dumps(value, ensure_ascii=True), flush=True)
    return report
