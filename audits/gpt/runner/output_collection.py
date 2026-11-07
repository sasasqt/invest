"""Copy untrusted container output into a bounded, link-free host snapshot.

POSIX hosts walk the output through open no-follow directory descriptors, so no
source access can pass through a link. Windows has no such descriptors. There the
walk uses paths, rejects every reparse point (symbolic links, junctions, WSL
links) before it opens anything, and re-checks each opened file's identity. That
walk relies on Docker having removed the container first (CONTRACT.md P1), so no
container process can swap an entry during collection (another local account still
can, CONTRACT.md I1). Neither walk replaces the container's own execution boundary.
"""

import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import contract

SUMMARY_NAMES = ("boundary.json", "environment.json", "benchmark-summary.json")
SUMMARY_MAX_BYTES = 64 * 1024
# Device names that Windows resolves in every folder, with or without an extension.
WINDOWS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
    + [port + digit for port in ("COM", "LPT") for digit in "0123456789¹²³"]
)
UNSAFE_CHARACTERS = frozenset('\\/:*?"<>|')
# An NTFS short name: at most 8 characters ending in ~digits, then up to 3 after a dot.
SHORT_NAME = re.compile(r"[^.]{0,7}~[0-9]+(\.[^.]{0,3})?")
DESCRIPTOR_APIS = (
    all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.scandir in os.supports_fd
)
METHODS = ("descriptor", "path")
# An exhausted descriptor table (the process limit, or the host's): the host's problem,
# never the output's. The descriptor walk holds two descriptors per folder level, the
# path walk one, so only the host's limit decides which walk meets it (I2).
DESCRIPTORS_EXHAUSTED = {errno.EMFILE, errno.ENFILE}
# Errors that describe the directory entry opened (absent, not a folder, a link under
# O_NOFOLLOW, permissions, a path too long): the output's. Any other error of a directory
# open (an exhausted descriptor table, ENOMEM, EIO) is the host's and is re-raised, so
# that collect_results names it and the test mode skips the I2 reference as it does for
# every OSError (a transient fault was reported as a walk disagreement otherwise).
ENTRY_ERRORS = {
    errno.ENOENT,
    errno.ENOTDIR,
    errno.ELOOP,
    errno.EACCES,
    errno.EPERM,
    errno.ENAMETOOLONG,
}
DEFAULT_METHOD = "descriptor" if DESCRIPTOR_APIS else "path"
# O_BINARY: without it Windows reads in text mode, rewriting CRLF and stopping at Ctrl-Z.
READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)


def log_line(tag, value, file=None):
    """Print untrusted text as one line that GitHub Actions cannot read as a command.

    json.dumps escapes newlines, so no line can start with '::'. The runner also
    parses the older '##[command]' form anywhere in a line, so '#' becomes \\u0023.
    """
    text = json.dumps(value, ensure_ascii=True).replace("#", "\\u0023")
    line = f"{tag} {text}"
    if contract.enabled():
        contract.require(
            "Q3",
            "\n" not in line
            and "\r" not in line
            and "#" not in line
            and not line.lstrip().startswith("::")
            and json.loads(text) == value,
            "log line is not one escaped line that decodes to its value",
        )
    print(line, file=file or sys.stdout, flush=True)


def portable_name(name):
    """True for one path component that Linux, Windows and artifact zips read as written.

    Windows opens a reserved name such as NUL as a device in any folder, and drops a
    trailing dot or space, so such names would reach a different file there. A name
    shaped like an NTFS short name (``PROGRA~1``) can name another file or folder.
    """
    if not name or any(
        character in UNSAFE_CHARACTERS or ord(character) < 32 or ord(character) == 127
        for character in name
    ):
        return False
    if name[-1] in ". " or name.split(".", 1)[0].rstrip(" ").upper() in WINDOWS_RESERVED:
        return False
    if len(name.split(".", 1)[0]) <= 8 and SHORT_NAME.fullmatch(name):
        return False
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:  # undecodable bytes (POSIX) or a lone surrogate (Windows)
        return False
    return True


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
def directory_fd(path, parent=None, lookup_only=False):
    """``lookup_only``: the folder is used only to look up a name, never listed. Linux
    then opens it with O_PATH, which needs search but not read permission, as the
    path walk does (CONTRACT.md I2)."""
    if not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise RejectedOutput("descriptor-based collection unavailable")
    access = getattr(os, "O_PATH", os.O_RDONLY) if lookup_only else os.O_RDONLY
    try:
        fd = os.open(path, access | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError as exc:
        if exc.errno not in ENTRY_ERRORS:
            raise  # the host's limit or fault: collect_results names it, not the output
        raise RejectedOutput("missing, linked or unreadable output directory") from exc
    try:
        yield fd
    finally:
        os.close(fd)


def is_link(info):
    """A POSIX symbolic link, or on Windows any reparse point (junctions included)."""
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def regular_file(info, device, maximum, too_large="output file size limit exceeded"):
    if (
        is_link(info)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_dev != device
    ):
        raise RejectedOutput("linked, special or cross-device output entry")
    if info.st_size > maximum:
        raise RejectedOutput(too_large)


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def same_identity(info, opened):
    return identity(info) == identity(opened)


def same_file(info, opened):
    """Windows: a by-name stat can carry the folder entry's older times and size, so
    only the file ID ties it to the open handle; size and times come from the handle."""
    return (info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino)


def read_opened(
    fd,
    info,
    device,
    maximum,
    changed,
    consume,
    same=same_identity,
    too_large="output file size limit exceeded",
):
    """Read an opened entry only while it is the regular file that was checked by name."""
    opened = os.fstat(fd)
    regular_file(opened, device, maximum, too_large)
    if not same(info, opened):
        raise RejectedOutput(changed)
    if contract.enabled():
        contract.require(
            "I1",
            not is_link(info)
            and stat.S_ISREG(opened.st_mode)
            and opened.st_nlink == 1
            and (info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino)
            and (same is same_file or identity(info) == identity(opened)),
            "about to read an entry that is not the one-link regular file checked by name",
        )
    while chunk := os.read(fd, 65536):
        consume(chunk)
    if identity(opened) != identity(os.fstat(fd)):
        raise RejectedOutput(changed)


class DescriptorFolder:
    """A folder reached only through open no-follow directory descriptors (POSIX)."""

    same = staticmethod(same_identity)

    def __init__(self, fd):
        self.fd = fd

    def names(self):
        with os.scandir(self.fd) as children:
            for entry in children:
                yield entry.name

    def lstat(self, name):
        return os.stat(name, dir_fd=self.fd, follow_symlinks=False)

    def open_file(self, name):
        return os.open(name, READ_FLAGS, dir_fd=self.fd)

    @contextmanager
    def child(self, name, info):
        with directory_fd(name, self.fd) as fd:
            opened = os.fstat(fd)
            if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
                raise RejectedOutput("output directory changed during collection")
            yield DescriptorFolder(fd)


class PathFolder:
    """A folder reached by path after each component was checked to be no link (Windows)."""

    same = staticmethod(same_file)

    def __init__(self, path, base, info):
        self.path, self.base, self.info = path, base, info

    def names(self):
        with os.scandir(self.path) as children:
            # scandir lists the folder the path named when it opened; make sure that
            # is still the folder checked by name before using any of its entries.
            unchanged_folder(self.path, self.info)
            for entry in children:
                yield entry.name

    def lstat(self, name):
        return os.lstat(os.path.join(self.path, name))

    def open_file(self, name):
        path = os.path.join(self.path, name)
        # Re-check the whole chain just before the open; read_opened then rejects
        # any file whose identity differs from the one checked here.
        current = self.base
        for part in Path(os.path.relpath(path, self.base)).parts:
            current = os.path.join(current, part)
            if is_link(os.lstat(current)):
                raise RejectedOutput("linked, special or cross-device output entry")
        return os.open(path, READ_FLAGS)

    @contextmanager
    def child(self, name, info):
        path = os.path.join(self.path, name)
        yield PathFolder(path, self.base, info)
        unchanged_folder(path, info)


def unchanged_folder(path, info):
    """Reject unless ``path`` still names the folder ``info`` was taken from, as no link."""
    after = os.lstat(path)
    if is_link(after) or (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino):
        raise RejectedOutput("output directory changed during collection")


def path_directory(path):
    """Stat a folder by path; it must exist and be a directory, not a link or reparse point."""
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise RejectedOutput("missing, linked or unreadable output directory") from exc
    if is_link(info) or not stat.S_ISDIR(info.st_mode):
        raise RejectedOutput("missing, linked or unreadable output directory")
    return info


@contextmanager
def open_folder(path, method, child=None):
    """Open ``path`` (or ``path/child``) for reading; yield the folder and its device."""
    if method == "descriptor":
        with directory_fd(path, lookup_only=child is not None) as parent:
            if child is None:
                yield DescriptorFolder(parent), os.fstat(parent).st_dev
                return
            with directory_fd(child, parent) as fd:
                yield DescriptorFolder(fd), os.fstat(fd).st_dev
        return
    # POSIX resolves a link before a later '..', as the descriptor walk does;
    # os.path.abspath would drop 'link/..' by text and walk another folder (I2).
    # An absolute path needs no current folder, which may have been deleted.
    if os.name == "nt":
        base = os.path.abspath(path)
    elif os.path.isabs(path):
        base = os.fspath(path)
    else:
        base = os.path.join(os.getcwd(), path)
    path_directory(base)
    folder = base if child is None else os.path.join(base, child)
    info = path_directory(folder)
    yield PathFolder(folder, base, info), info.st_dev
    after = path_directory(folder)
    if (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino):
        raise RejectedOutput("output directory changed during collection")


def parse_summary(payload):
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
        # json.loads accepts NaN and Infinity; they are not JSON, so reject them.
        json.dumps(value, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RejectedOutput("invalid JSON summary") from exc
    return value


def read_summaries(snapshot, method=None):
    """Read only the private host snapshot, never the original /work tree."""
    method = method or DEFAULT_METHOD
    summaries = {}
    with open_folder(snapshot, method) as (folder, device):
        for name in SUMMARY_NAMES:
            try:
                info = folder.lstat(name)
            except FileNotFoundError:
                continue
            except OSError as exc:
                # The path walk looks a name up by its full path. copy_tree wrote every
                # snapshot file by the snapshot's own spelling, so when that spelling is
                # absolute, a name past the limit is absent (I2). A relative spelling is
                # looked up as the current folder plus that spelling, a longer path than
                # copy_tree used, so there the lookup fails and the path walk rejects.
                if exc.errno != errno.ENAMETOOLONG or not os.path.isabs(snapshot):
                    raise
                continue
            regular_file(info, device, SUMMARY_MAX_BYTES, "summary size limit exceeded")
            payload = bytearray()

            def consume(chunk, payload=payload):
                payload.extend(chunk)
                if len(payload) > SUMMARY_MAX_BYTES:
                    raise RejectedOutput("summary size limit exceeded")

            fd = folder.open_file(name)
            try:
                read_opened(
                    fd,
                    info,
                    device,
                    SUMMARY_MAX_BYTES,
                    "summary changed during collection",
                    consume,
                    folder.same,
                    "summary size limit exceeded",
                )
            finally:
                os.close(fd)
            summaries[name] = parse_summary(bytes(payload))
    return summaries


def copy_opened(fd, info, device, destination, limits, counts, same):
    """Copy one checked, opened file into the snapshot; return its size and SHA-256."""
    digest, copied = hashlib.sha256(), 0
    with destination.open("xb") as output:

        def consume(chunk):
            nonlocal copied
            copied += len(chunk)
            counts["bytes"] += len(chunk)
            if copied > limits.file_bytes or counts["bytes"] > limits.total_bytes:
                raise RejectedOutput("output byte limit exceeded")
            output.write(chunk)
            digest.update(chunk)

        read_opened(
            fd,
            info,
            device,
            limits.file_bytes,
            "output file changed during collection",
            consume,
            same,
        )
    return copied, digest.hexdigest()


def copy_tree(work, snapshot, limits, method):
    """Copy ``work/results`` into the empty ``snapshot``; return records and counts."""
    records, counts = [], {"entries": 0, "bytes": 0}

    def walk(folder, target, prefix, depth, device):
        if depth > limits.depth:
            raise RejectedOutput("output directory depth limit exceeded")
        for name in folder.names():
            if not portable_name(name):
                raise RejectedOutput("unsafe artifact filename")
            counts["entries"] += 1
            if counts["entries"] > limits.entries:
                raise RejectedOutput("output entry count limit exceeded")
            info = folder.lstat(name)
            relative = prefix / name
            if stat.S_ISDIR(info.st_mode) and not is_link(info):
                if info.st_dev != device:
                    raise RejectedOutput("cross-device output directory")
                with folder.child(name, info) as child:
                    output_folder = target / name
                    output_folder.mkdir(mode=0o700)
                    walk(child, output_folder, relative, depth + 1, device)
                continue
            regular_file(info, device, limits.file_bytes)
            fd = folder.open_file(name)
            try:
                copied, digest = copy_opened(
                    fd, info, device, target / name, limits, counts, folder.same
                )
            finally:
                os.close(fd)
            records.append({"path": relative.as_posix(), "bytes": copied, "sha256": digest})

    with open_folder(work, method, "results") as (root, device):
        walk(root, snapshot, Path(), 0, device)
    return records, counts["entries"], counts["bytes"]


# A full host volume (or quota): the snapshot's problem, never the output's.
VOLUME_FULL = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


def private_folder(parent):
    """A new ``.collect-*`` folder in ``parent``, named the way ``parent`` is spelled.

    Python 3.12+ mkdtemp returns os.path.abspath of the folder it made, which on POSIX
    drops 'link/..' by text and so can name a folder elsewhere than the one it made."""
    return Path(parent, Path(tempfile.mkdtemp(prefix=".collect-", dir=parent)).name)


def remove_snapshot(snapshot):
    """Remove a private ``.collect-*`` snapshot. ``shutil.rmtree`` holds a descriptor per
    folder level, so after a rejection for an exhausted descriptor table it can run out
    too and leave the snapshot behind (Q2); then the tree is removed bottom-up with one
    listing open at a time. The snapshot is this process's own: mode 0o700, no links."""
    try:
        shutil.rmtree(snapshot)
    except OSError as exc:
        if exc.errno not in DESCRIPTORS_EXHAUSTED:
            raise
        for current, folders, files in os.walk(snapshot, topdown=False):
            for name in files:
                os.unlink(os.path.join(current, name))
            for name in folders:
                os.rmdir(os.path.join(current, name))
        os.rmdir(snapshot)


def collect_results(work, destination, limits=DEFAULT_LIMITS, method=None):
    """Reject unsafe output atomically; return data only from the safe snapshot.

    Call after Docker has stopped every container process. On POSIX all source
    traversal stays relative to open no-follow directory descriptors, including the
    results root; on Windows every entry is checked by path before it is opened. No
    link is passed on to an artifact uploader.
    """
    method = method or DEFAULT_METHOD
    if method not in METHODS:
        raise ValueError("unknown collection method")
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
    snapshot = private_folder(destination.parent)
    try:
        records, entries, byte_count = copy_tree(work, snapshot, limits, method)
        summaries = read_summaries(snapshot, method)
        snapshot.rename(destination)
    except (OSError, RejectedOutput) as exc:
        remove_snapshot(snapshot)
        if contract.enabled():
            check_rejected(work, destination, snapshot, limits, method, exc)
        if isinstance(exc, RejectedOutput):
            raise
        if exc.errno in VOLUME_FULL:
            raise RejectedOutput("host volume full during collection") from exc
        if exc.errno in DESCRIPTORS_EXHAUSTED:
            raise RejectedOutput("host descriptor limit reached during collection") from exc
        raise RejectedOutput("unreadable or changing output entry") from exc
    except BaseException:
        remove_snapshot(snapshot)
        raise
    report = {
        "status": "collected",
        "limits": asdict(limits),
        "entries": entries,
        "bytes": byte_count,
        "files": sorted(records, key=lambda row: row["path"]),
        "summaries": summaries,
    }
    if contract.enabled():
        check_collected(work, destination, report, limits, method)
    return report


def collect_workload(work, results, limits=DEFAULT_LIMITS, method=None):
    """The runner and Docker acceptance harness share this exact host sink."""
    results = Path(results)
    try:
        report = collect_results(work, results / "workload", limits, method)
    except RejectedOutput as exc:
        report = {"status": "rejected", "reason": str(exc), "limits": asdict(limits)}
    (results / "collection.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8", newline="\n"
    )
    if contract.enabled():
        recorded = json.loads((results / "collection.json").read_text(encoding="utf-8"))
        contract.require("Q2", recorded["status"] == report["status"], "collection.json differs")
    log_line("AUDIT_COLLECTION", {"status": report["status"]})
    for name, value in report.get("summaries", {}).items():
        log_line("AUDIT_EVIDENCE " + name, value)
    return report


# Contract checks (CONTRACT.md); they run only when CONTRACT_CHECKS=1.


def other_method_outcome(work, limits, method, beside):
    """I2: run the other walk on the same tree; return its outcome and data.

    Its snapshot is made where the real one was (``beside``), under a name of the same
    length, so it fits the path limit wherever the real snapshot did; one in TMPDIR
    could be longer and fail on a tree the real walk collected."""
    other = "path" if method == "descriptor" else "descriptor"
    snapshot = private_folder(beside)
    # The spelling copy_tree gives its errors (pathlib drops a leading './').
    scratch = os.fspath(snapshot)
    try:
        records, entries, byte_count = copy_tree(work, snapshot, limits, other)
        summaries = read_summaries(snapshot, other)
    except (OSError, RejectedOutput) as exc:
        # A failure on the reference snapshot's own path says nothing about the tree;
        # as an outcome it could pass for path_too_long. A full volume (a write or
        # close carries no file name) can only be the snapshot's: the tree is only read.
        # An exhausted descriptor table says nothing about the tree either.
        name = getattr(exc, "filename", None)
        if getattr(exc, "errno", None) in VOLUME_FULL | DESCRIPTORS_EXHAUSTED or (
            isinstance(name, (str, bytes))
            and (os.fsdecode(name) == scratch or os.fsdecode(name).startswith(scratch + os.sep))
        ):
            raise
        return "rejected", exc
    finally:
        remove_snapshot(snapshot)
    return "collected", sorted(records, key=lambda row: row["path"]), entries, byte_count, summaries


def check_rejected(work, destination, snapshot, limits, method, error):
    contract.require(
        "Q2",
        not destination.exists() and not destination.is_symlink() and not snapshot.exists(),
        "a rejected collection left a snapshot or destination",
    )
    # I2 compares walks of one unchanging tree. A tree that changed during the walk
    # (a test that injects the change, or another local account, see CONTRACT.md I1)
    # may be stable and valid by now.
    changed = isinstance(error, OSError) or "changed during collection" in str(error)
    if method == "descriptor" and DESCRIPTOR_APIS and not changed:
        outcome = other_method_outcome(work, limits, method, destination.parent)
        contract.require("I2", outcome[0] == "rejected", "only the descriptor walk rejected")


def chain_entry_expected(info, last):
    """No link anywhere, a folder on the way and a regular file at the end (Q1)."""
    kind = stat.S_ISREG if last else stat.S_ISDIR
    return not is_link(info) and kind(info.st_mode)


def source_chain(work, relative):
    """Q1: lstat each component of work/results/relative and read the file, following
    no link. POSIX walks descriptors, so a path past PATH_MAX that the descriptor walk
    collected can be checked too. An unexpected entry stops the walk with no bytes
    read, so that check_collected names the broken rule (Q1); so does a missing one."""
    parts = ("results", *relative.split("/"))
    chain = []
    if not DESCRIPTOR_APIS:
        current = Path(work)
        for index, part in enumerate(parts):
            current = current / part
            try:
                chain.append(os.lstat(current))
            except FileNotFoundError:
                return chain, None
            if not chain_entry_expected(chain[-1], index == len(parts) - 1):
                return chain, None
        return chain, current.read_bytes()
    flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(work, flags)
    try:
        for index, part in enumerate(parts):
            try:
                chain.append(os.stat(part, dir_fd=fd, follow_symlinks=False))
            except FileNotFoundError:
                return chain, None
            if not chain_entry_expected(chain[-1], index == len(parts) - 1):
                return chain, None
            if index < len(parts) - 1:
                parent, fd = fd, os.open(part, flags, dir_fd=fd)
                os.close(parent)
        with os.fdopen(os.open(parts[-1], READ_FLAGS, dir_fd=fd), "rb") as stream:
            return chain, stream.read()
    finally:
        os.close(fd)


def path_too_long(outcome):
    """The path walk cannot open a path past the host's limit; the descriptor walk can.
    The path walk wraps that OSError (for the results folder, in path_directory), so
    the cause chain is followed."""
    error = outcome[1] if outcome[0] == "rejected" else None
    while error is not None:
        if getattr(error, "errno", None) == errno.ENAMETOOLONG:
            return True
        error = error.__cause__
    return False


def snapshot_walk(destination):
    """Yield (folder, folders, files, lstat of a name, bytes of a file) for each folder of
    the collected snapshot. The snapshot was written under its shorter .collect-* name, so
    a longer destination name can put a collected path past PATH_MAX; POSIX therefore
    lists and reads it through descriptors, as source_chain does the source."""
    if not (DESCRIPTOR_APIS and hasattr(os, "fwalk")):
        for current, directories, files in os.walk(destination):
            yield (
                current,
                directories,
                files,
                lambda name, current=current: os.lstat(os.path.join(current, name)),
                lambda name, current=current: Path(current, name).read_bytes(),
            )
        return
    for current, directories, files, fd in os.fwalk(destination):

        def read(name, fd=fd):
            with os.fdopen(os.open(name, READ_FLAGS, dir_fd=fd), "rb") as stream:
                return stream.read()

        yield (
            current,
            directories,
            files,
            lambda name, fd=fd: os.stat(name, dir_fd=fd, follow_symlinks=False),
            read,
        )


def check_collected(work, destination, report, limits, method):
    found, folders = {}, 0
    for current, directories, files, lstat, read in snapshot_walk(destination):
        for name in directories + files:
            info = lstat(name)
            contract.require(
                "Q1",
                not is_link(info) and (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)),
                "the snapshot holds a link or special entry",
            )
        folders += len(directories)
        for name in files:
            found[Path(current, name).relative_to(destination).as_posix()] = read(name)
    rows = {row["path"]: row for row in report["files"]}
    contract.require("Q1", set(found) == set(rows), "snapshot files differ from the records")
    contract.require("Q1", report["entries"] == folders + len(found), "entry count differs")
    contract.require("Q1", report["entries"] <= limits.entries, "entry limit exceeded")
    contract.require("Q1", report["bytes"] == sum(len(data) for data in found.values()))
    contract.require("Q1", report["bytes"] <= limits.total_bytes, "total byte limit exceeded")
    for relative, data in found.items():
        row = rows[relative]
        contract.require("Q1", row["bytes"] == len(data) <= limits.file_bytes, relative)
        contract.require("Q1", row["sha256"] == hashlib.sha256(data).hexdigest(), relative)
        chain, source = source_chain(work, relative)
        contract.require("Q1", chain, "no source results folder: " + relative)
        device = chain[0].st_dev  # the results folder, reached without its full path
        for info in chain:
            contract.require("Q1", not is_link(info) and info.st_dev == device, relative)
        contract.require("Q1", stat.S_ISREG(info.st_mode) and info.st_nlink == 1, relative)
        contract.require("Q1", source == data, "source bytes differ: " + relative)
    if method == "descriptor" and DESCRIPTOR_APIS:
        outcome = other_method_outcome(work, limits, method, destination.parent)
        if path_too_long(outcome):
            return
        expected = ("collected", report["files"], report["entries"], report["bytes"])
        contract.require("I2", outcome[:4] == expected, "the two walks copied different data")
        contract.require("I2", outcome[4] == report["summaries"], "the two walks read summaries")
