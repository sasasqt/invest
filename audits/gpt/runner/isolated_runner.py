"""Prepare a container-only audit on a Docker-capable disposable runner.

The host performs metadata reads and image setup only. Repository code runs only
in the final container, with no network, publishing credentials or host home mount.
The host side runs on Linux and Windows; the container is always Linux.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path

import contract
from output_collection import collect_workload, is_link, log_line, portable_name

# Always the local daemon; DOCKER_HOST and contexts are removed from the environment.
DOCKER_ENDPOINT = (
    "npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock"
)
GIT_TIMEOUT = 600
# Windows has no system bundle: "/etc/..." there names a folder on the current drive.
SYSTEM_CA_BUNDLE = None if os.name == "nt" else "/etc/ssl/certs/ca-certificates.crt"
SERVER_AUTH = "1.3.6.1.5.5.7.3.1"
# Docker reads --mount and --secret values as CSV fields (Go's encoding/csv).
CSV_MARKS = (",", '"', "\n", "\r")


def host_tool(name):
    """The absolute path of program ``name`` in an absolute PATH folder, or None.

    Never the current folder: Windows looks there before PATH (shutil.which, and
    CreateProcess for a bare name), and POSIX does for a relative PATH entry, so a
    git, uv or docker committed in an audited checkout would run on the host when
    the runner starts inside it.
    """
    suffixes = [""]
    if os.name == "nt":
        listed = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").lower().split(";")
        if not any(name.lower().endswith(suffix) for suffix in listed if suffix):
            suffixes = [suffix for suffix in listed if suffix]
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        # On Windows also a drive or share: "\\tools" is relative to the current drive.
        if not os.path.isabs(folder) or (os.name == "nt" and not os.path.splitdrive(folder)[0]):
            continue
        for suffix in suffixes:
            candidate = os.path.join(folder, name + suffix)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def program(name):
    """``host_tool``, or an error rather than letting the OS search for a bare name."""
    found = host_tool(name)
    if not found:
        raise RuntimeError(f"{name} executable unavailable on PATH")
    return found


def docker_command(*args):
    """The Docker CLI from an absolute PATH folder, aimed at the local daemon."""
    return [program("docker"), f"--host={DOCKER_ENDPOINT}", *args]


def write_text(path, text):
    """UTF-8 with LF line ends on every host (Windows defaults to its code page and CRLF)."""
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def run_captured(argv, *, timeout=None, input=None, **kwargs):
    """Run ``argv`` with captured output; on a timeout kill it and raise at once.

    Every host program but the container run (``run_bounded``, which reads its log on
    a thread with its own deadline) goes through here, not subprocess.run: on
    Windows, run reads the pipes to their end after the kill, so a launcher's child
    that still holds them (Git for Windows' cmd\\git.exe, a Docker CLI plugin such
    as buildx) would keep it waiting past the timeout. ``input`` (bytes) is passed as
    a file, not a pipe: Python 3.11 on Windows writes a pipe's input before it starts
    timing, so a program that stopped reading would hold it past the timeout too.
    """
    feed = None
    if input is not None:
        feed = tempfile.TemporaryFile()
        feed.write(input)
        feed.seek(0)
    try:
        process = subprocess.Popen(
            argv, stdin=feed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
        )
    finally:
        if feed is not None:
            feed.close()  # the program has its own handle
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:  # the timeout, and an interrupt, as subprocess.run does
        process.kill()
        process.wait(timeout=30)
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def checked(argv, *, timeout=None, **kwargs):
    result = run_captured(
        argv, timeout=timeout, text=True, encoding="utf-8", errors="replace", **kwargs
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(argv[0]).name} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def checked_path(argv, *, timeout=None, **kwargs):
    """The one path a program prints, decoded as the file system decodes names, so a
    folder name that is not valid UTF-8 keeps its bytes (``checked`` replaces them).

    Windows: Git prints paths in UTF-8 there. That is Python's file-name encoding too,
    unless PYTHONLEGACYWINDOWSFSENCODING=1 selects the ANSI code page, which would
    turn a folder named with an accented letter into another name."""
    result = run_captured(argv, timeout=timeout, **kwargs)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"{Path(argv[0]).name} exited {result.returncode}: {message}")
    line = result.stdout.removesuffix(b"\n")
    if os.name == "nt":
        return Path(line.removesuffix(b"\r").decode("utf-8", "surrogatepass"))
    return Path(os.fsdecode(line))


def run_bounded(argv, *, env=None, timeout=6600, max_log_bytes=8 * 1024 * 1024):
    """Bound host memory while retaining a failed container's available log.

    A reader thread drains the pipe, because selectors cannot wait on pipes on
    Windows. The pipe is closed only once that thread has stopped reading: closing
    it under a blocked read could hang, or let the thread read a reused descriptor.
    If a grandchild still holds the pipe when this returns, the reader closes it.
    """
    if timeout <= 0 or max_log_bytes <= 0:
        raise ValueError("execution limits must be positive")
    deadline = time.monotonic() + timeout
    chunks, lock, over, failure = [], threading.Lock(), threading.Event(), []
    finished = {"reader": False, "caller": False}
    process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pipe = process.stdout

    def finish(side):
        """Whichever of the reader and the caller finishes last closes the pipe."""
        with lock:
            finished[side] = True
            last = all(finished.values())
        if last:
            pipe.close()

    def drain():
        size = 0
        try:
            while data := pipe.read1(65536):
                with lock:
                    if size < max_log_bytes:
                        chunks.append(data[: max_log_bytes - size])
                    size += len(data)
                if size > max_log_bytes:
                    over.set()
                    return
        except (OSError, ValueError) as error:
            failure.append(error)
        finally:
            finish("reader")

    reader = threading.Thread(target=drain, name="run_bounded-reader", daemon=True)
    reason = None
    try:
        reader.start()
        while reader.is_alive() or process.poll() is None:
            if over.is_set():
                reason = "log_limit"
                break
            if failure:  # nothing drains the pipe any more, so waiting cannot help
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "timeout"
                break
            if reader.is_alive():
                reader.join(min(0.1, remaining))
            else:  # the output is closed but the child still runs: wait, do not spin
                try:
                    process.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
        if over.is_set():
            reason = "log_limit"
    finally:
        try:
            if process.poll() is None:
                process.kill()
            status = process.wait(timeout=30)
        finally:
            if reader.ident is None:  # the thread never started
                finish("reader")
            else:
                reader.join(timeout=5)
            finish("caller")
    if failure:
        raise RuntimeError("container log reader failed") from failure[0]
    if reason:
        status = 124 if reason == "timeout" else 125
    with lock:
        output = b"".join(chunks)
    return subprocess.CompletedProcess(argv, status, output.decode(errors="replace"), ""), reason


def remove_container(name, env):
    """Do not collect a bind mount while a container could still write it."""
    run_captured(docker_command("container", "rm", "--force", name), env=env, timeout=30)
    remaining = checked(
        docker_command(
            "container", "ls", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.ID}}"
        ),
        env=env,
        timeout=30,
    )
    if remaining:
        raise RuntimeError("Container removal unverified; output collection blocked")
    return True


def container_user():
    """Run as the invoking user; root, and Windows (no POSIX IDs), map to nobody."""
    if os.name == "nt":
        return 65534, 65534
    return os.getuid() or 65534, os.getgid() or 65534


def ca_bundle(output):
    """Find the CA bundle that the image build reads as a BuildKit secret (never stored).

    Linux: the system bundle. Otherwise Python's default CA file, and on Windows the
    certificate store (the roots and intermediates Python itself trusts for HTTPS),
    exported once as PEM into the run's private output folder.

    A file whose path Docker's comma-separated --secret value would split (a comma, a
    double quote or a line break, which SSL_CERT_FILE may hold) is copied into that
    folder first; main refused such a character there.
    """
    for candidate in (SYSTEM_CA_BUNDLE, ssl.get_default_verify_paths().cafile):
        if candidate and Path(candidate).is_file():
            if any(mark in str(candidate) for mark in CSV_MARKS):
                copied = Path(output) / "build-ca-bundle.pem"
                shutil.copyfile(candidate, copied)
                return copied
            return Path(candidate)
    if os.name == "nt":
        certificates = [
            ssl.DER_cert_to_PEM_cert(certificate)
            for store in ("ROOT", "CA")
            for certificate, encoding, trust in ssl.enum_certificates(store)
            if encoding == "x509_asn" and (trust is True or SERVER_AUTH in trust)
        ]
        if certificates:
            exported = Path(output) / "build-ca-bundle.pem"
            write_text(exported, "".join(dict.fromkeys(certificates)))
            return exported
    raise RuntimeError("No CA bundle found for the image build")


def execution_command(image, source, output, tools, sentinel, host_pid, uid, gid):
    if uid <= 0 or gid < 0:
        raise ValueError("Container execution requires an unprivileged UID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Execution requires a recorded immutable image ID")
    command = docker_command(
        "run",
        "--rm",
        # The workload must be the container's first process (CONTRACT.md W2); a daemon
        # configured with "init": true would put docker-init there instead.
        "--init=false",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=2g",
        "--cpus=2",
        "--user",
        f"{uid}:{gid}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m",
    )
    for src, dest, readonly in (
        (source, "/input", True),
        (tools, "/audit", True),
        (output, "/work", False),
    ):
        text = str(Path(src).resolve())
        if any(mark in text for mark in CSV_MARKS):
            raise ValueError(
                "A mount path must not contain a comma, a double quote or a line break"
            )
        command += [
            "--mount",
            f"type=bind,src={text},dst={dest}" + (",readonly" if readonly else ""),
        ]
    for name, value in {
        "HOME": "/work/home",
        "MPLCONFIGDIR": "/work/matplotlib",
        "TMPDIR": "/work/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONHASHSEED": "0",
        # The Docker CLI adds each of these, in both cases, from the `proxies` of its
        # config.json (a proxy URL can hold a password) unless the run sets it.
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "FTP_PROXY": "",
        "ALL_PROXY": "",
        "NO_PROXY": "",
        "http_proxy": "",
        "https_proxy": "",
        "ftp_proxy": "",
        "all_proxy": "",
        "no_proxy": "",
    }.items():
        command += ["--env", f"{name}={value}"]
    command += [image, "python", "/audit/runner_workload.py"]
    return command + boundary_arguments(sentinel, host_pid)


def boundary_arguments(sentinel, host_pid, windows=os.name == "nt"):
    """Arguments for the container's outside-file and host-process probes.

    Both probes name a host object as the Linux container would see it. On a Windows
    host, a path such as C:\\... or a Windows process ID names nothing inside the
    Linux VM, so the probes would pass whatever leaked; they are not run there.
    """
    if windows or sentinel is None or host_pid is None:
        return []
    return ["--sentinel", str(sentinel), "--host-pid", str(host_pid)]


def blob_digest(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


def git_environment(isolated=False):
    """Environment for every Git call that reads the source or builds the staged copy.

    Inherited GIT_* variables (GIT_DIR, GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY...) would
    point Git at another repository, and replace refs would swap the commit's tree
    for another one. Git before 2.43 let a configured core.useReplaceRefs=true win
    over GIT_NO_REPLACE_OBJECTS, so the setting is also passed as command-line
    configuration, which Git 2.31 and later (every Git that require_git accepts)
    reads last. Grafts (``info/grafts``, replace refs' deprecated predecessor) would
    rewrite a commit's parents, so packing its history would take another branch:
    Git reads an empty graft file instead, without its hint about grafts. A commit-graph
    file or a pack bitmap in the store caches parents and reachability as they were
    when it was written (a bitmap Git wrote under a graft keeps the grafted history;
    a corrupted or planted commit-graph can name any parent), so packing and the
    history listings read the commit objects themselves and use neither.
    ``isolated`` also drops system and global configuration.
    """
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0", GIT_GRAFT_FILE=os.devnull)
    settings = {
        "core.useReplaceRefs": "false",
        "advice.graftFileDeprecated": "false",
        "core.commitGraph": "false",
        "pack.useBitmaps": "false",
    }
    env["GIT_CONFIG_COUNT"] = str(len(settings))
    for index, (key, value) in enumerate(settings.items()):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    if isolated:
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def git_metadata_name(name):
    """True for ``.git`` in any case, and for its Windows short name ``GIT~1``."""
    return name.casefold() in (".git", "git~1")


def source_entries(listing):
    """Parse ``git ls-tree -rz`` output; keep only paths every host can write as named."""
    entries, kinds = [], {}
    for item in listing.split(b"\0"):
        if not item:
            continue
        header, raw = item.split(b"\t", 1)
        mode, kind, digest = header.decode("ascii").split()
        if mode not in ("100644", "100755") or kind != "blob":
            raise ValueError("Only ordinary tracked files are allowed in the source fixture")
        try:
            path = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Source path is not valid UTF-8") from None
        parts = path.split("/")
        if any(git_metadata_name(part) for part in parts):
            # Git refuses such paths in a checkout; written into the staged copy, they
            # could give the host's own Git commands configuration from the commit.
            raise ValueError(f"Source path enters Git metadata: {path}")
        if not all(portable_name(part) for part in parts):
            raise ValueError(f"Source path is not portable to Windows and Linux: {path}")
        # A crafted tree object can list one path twice.
        if path.casefold() in kinds:
            raise ValueError(f"Source path listed twice, or clash when case is ignored: {path}")
        # Windows folds case: two paths that differ only by case would overwrite each
        # other there, so both hosts refuse them.
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            kind_of = (prefix, depth == len(parts))
            if kinds.setdefault(prefix.casefold(), kind_of) != kind_of:
                raise ValueError(f"Source paths clash when case is ignored: {path}")
        entries.append((path, mode, digest))
    return entries


def read_blobs(source, digests):
    """Read each blob from Git's object store, not from the checked-out files.

    Git on Windows checks text out with CRLF line ends, so checked-out bytes need not
    match the commit; the object store always holds the committed bytes.
    """
    request = "".join(digest + "\n" for digest in digests).encode("ascii")
    result = run_captured(
        [program("git"), "-C", str(source), "cat-file", "--batch"],
        input=request,
        env=git_environment(),
        timeout=GIT_TIMEOUT,
    )
    if result.returncode:
        raise RuntimeError(f"git cat-file exited {result.returncode}")
    output, offset, blobs = result.stdout, 0, []
    for digest in digests:
        end = output.find(b"\n", offset)
        header = output[offset:end].decode("ascii", "replace").split() if end >= 0 else []
        if len(header) != 3 or header[:2] != [digest, "blob"] or not header[2].isdigit():
            raise ValueError(f"Git object missing or not a blob: {digest}")
        start, size = end + 1, int(header[2])
        payload = output[start : start + size]
        if len(payload) != size or output[start + size : start + size + 1] != b"\n":
            raise ValueError(f"Git object output ended early: {digest}")
        if blob_digest(payload) != digest:
            raise ValueError(f"Git object does not match its digest: {digest}")
        blobs.append(payload)
        offset = start + size + 1
    if offset != len(output):
        raise ValueError("Unexpected git cat-file output")
    return blobs


def make_folders(folder, created):
    """Create each staged folder exactly once.

    A folder that already exists means two committed paths name the same folder on
    this host (an NTFS short name, for example); merging them would stage a layout
    that is not the commit.
    """
    missing = []
    while folder not in created:
        missing.append(folder)
        folder = folder.parent
    for folder in reversed(missing):
        try:
            folder.mkdir()
        except FileExistsError:
            raise ValueError(f"Source paths alias each other on this host: {folder}") from None
        created.add(folder)


def require_git():
    """Refuse a Git that would not keep staging isolated.

    Git before 2.32 ignores GIT_CONFIG_GLOBAL, so the staged index would be built
    with the host user's global configuration; before 2.31 it also misreads
    ``rev-parse --path-format``.
    """
    version = checked([program("git"), "--version"], env=git_environment(), timeout=60)
    found = re.match(r"git version (\d+)\.(\d+)", version)
    if not found or (int(found[1]), int(found[2])) < (2, 32):
        raise RuntimeError(f"Staging needs Git 2.32 or later, found: {version[:80]}")


def stage_source(source, staged, expected_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Expected revision must be a full Git SHA")
    require_git()
    env = git_environment()
    actual = checked(
        [program("git"), "-C", str(source), "rev-parse", "HEAD"], env=env, timeout=GIT_TIMEOUT
    )
    if actual != expected_sha:
        raise ValueError("Source HEAD differs from the expected revision")
    # --full-tree: from a subfolder of the checkout, ls-tree would list only that
    # subtree, relative to it, and stage it as if it were the whole commit (Q4).
    listing = run_captured(
        [program("git"), "-C", str(source), "ls-tree", "-rz", "--full-tree", expected_sha],
        env=env,
        timeout=GIT_TIMEOUT,
    )
    if listing.returncode:
        message = listing.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git exited {listing.returncode}: {message}")
    entries = source_entries(listing.stdout)
    staged.mkdir()
    # Git's own folder exists before any source file is written, so no committed path
    # can land in it, even one that a name check above missed.
    (staged / ".git").mkdir()
    created, records = {staged}, []
    for (path, mode, digest), payload in zip(
        entries, read_blobs(source, [digest for _, _, digest in entries]), strict=True
    ):
        destination = staged.joinpath(*path.split("/"))
        make_folders(destination.parent, created)
        try:
            stream = destination.open("xb")  # never overwrite another committed path
        except FileExistsError:
            raise ValueError(f"Source paths alias each other on this host: {path}") from None
        with stream:
            stream.write(payload)
        destination.chmod(0o755 if mode == "100755" else 0o644)
        if contract.enabled():
            contract.require("Q4", blob_digest(destination.read_bytes()) == digest, path)
        records.append({"path": path, "git_blob": digest})
    if contract.enabled():
        written = sorted(
            item.relative_to(staged).as_posix()
            for item in staged.rglob("*")
            if item.is_file() and item.relative_to(staged).parts[0] != ".git"
        )
        contract.require(
            "Q4", written == sorted(path for path, _, _ in entries), "staged paths differ"
        )
    # Keep genuine commit provenance, but never copy Git credentials, config,
    # hooks, logs, alternates or global/home files into the execution boundary.
    # The common Git folder: a linked worktree's own Git folder holds no objects.
    git_dir = checked_path(
        [
            program("git"),
            "-C",
            str(source),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        env=env,
        timeout=GIT_TIMEOUT,
    )
    if not (git_dir / "objects").is_dir():
        raise ValueError(f"No Git object store in the common Git folder: {git_dir}")
    if (git_dir / "objects/info/alternates").exists():
        raise ValueError("Materialize Git objects locally before staging")
    for path in (git_dir / "objects").rglob("*"):
        if is_link(path.lstat()):  # symbolic links, and junctions on Windows
            raise ValueError("Symlink in Git object store")
    (staged / ".git/objects/pack").mkdir(parents=True)
    (staged / ".git/refs").mkdir()
    write_text(staged / ".git/HEAD", expected_sha + "\n")
    # Windows has no executable bit, so Git there must not compare file modes.
    filemode = "false" if os.name == "nt" else "true"
    write_text(
        staged / ".git/config",
        f"[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = {filemode}\n",
    )
    if (git_dir / "shallow").is_file():
        shallow = (git_dir / "shallow").read_text(encoding="ascii")
        if not all(re.fullmatch(r"[0-9a-f]{40}", x) for x in shallow.splitlines()):
            raise ValueError("Invalid shallow-boundary metadata")
        write_text(staged / ".git/shallow", shallow)
    # Only the objects the audited commit reaches (its history, cut at a shallow
    # boundary), packed by Git: the store also holds stashes (with `-u`, untracked
    # files such as .env), other branches and blobs once added but never committed,
    # and the audited code must not read those. The pack goes to stdout and is
    # indexed in the staged copy: a pack Git writes to a named file starts as a
    # temporary file in the store of the repository it runs in, so packing in the
    # source would write there (a read-only checkout fails) and then rename across
    # volumes (an --output on another file system or drive fails).
    packed = run_captured(
        [program("git"), "-C", str(source), "pack-objects", "--revs", "--stdout", "--quiet"],
        input=f"{expected_sha}\n".encode("ascii"),
        env=env,
        timeout=GIT_TIMEOUT,
    )
    if packed.returncode:
        message = packed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git exited {packed.returncode}: {message}")
    indexed = run_captured(
        [program("git"), "-C", str(staged), "index-pack", "--stdin"],
        input=packed.stdout,
        env=git_environment(isolated=True),
        timeout=GIT_TIMEOUT,
    )
    if indexed.returncode:
        message = indexed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git exited {indexed.returncode}: {message}")
    # The index is built with no inherited, system or global configuration, no file
    # system monitor command and an empty hooks folder: nothing from the commit or
    # the host user's setup runs here.
    with tempfile.TemporaryDirectory() as hooks:
        checked(
            [
                program("git"),
                "-C",
                str(staged),
                "-c",
                "core.fsmonitor=",  # empty is "off" on every Git version
                "-c",
                f"core.hooksPath={Path(hooks).as_posix()}",
                "reset",
                "--mixed",
                expected_sha,
            ],
            env=git_environment(isolated=True),
            timeout=GIT_TIMEOUT,
        )
    # The staged store must hold exactly what the commit reaches as the staged copy
    # itself reads its history (its own shallow file, no grafts, replace refs or
    # caches, objects named by their content when the pack was indexed). Packing read
    # the source through its object index (a pack .idx or a multi-pack-index): an
    # index whose entry for a commit in the history points at another object (a
    # corrupted or planted index; `git multi-pack-index verify` reports one) makes
    # Git pack that object's tree instead, and no configuration switches an index
    # off, so the staged copy is compared here on every run, not only in test mode.
    staged_objects = checked(
        [
            program("git"),
            "-C",
            str(staged),
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname)",
        ],
        env=git_environment(isolated=True),
        timeout=GIT_TIMEOUT,
    )
    own = run_captured(
        [
            program("git"),
            "-C",
            str(staged),
            "rev-list",
            "--objects",
            "--no-object-names",
            expected_sha,
        ],
        env=git_environment(isolated=True),
        timeout=GIT_TIMEOUT,
    )
    if own.returncode:
        # Git's own words: a missing object (a bent source index) reads as "unable to
        # read tree"; a host fault (memory, a signal) must not read as a difference.
        message = own.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"Staged Git history could not be listed: git exited {own.returncode}: {message}"
        )
    if set(staged_objects.split()) != set(own.stdout.decode("ascii", "replace").split()):
        raise ValueError("Staged Git objects differ from the commit's history")
    if contract.enabled():
        # The source's own listing must agree too, so a view of the source that both
        # packing and the staged copy share cannot hide a missing or extra object.
        reached = checked(
            [
                program("git"),
                "-C",
                str(source),
                "rev-list",
                "--objects",
                "--no-object-names",
                expected_sha,
            ],
            env=env,
            timeout=GIT_TIMEOUT,
        )
        contract.require(
            "Q4",
            set(staged_objects.split()) == set(reached.split()),
            "staged Git objects differ from the source's listing of the commit's history",
        )
    return records


def blocked(results, reason):
    write_text(
        results / "runner.json", json.dumps({"status": "blocked", "reason": reason}, indent=2)
    )
    print(f"BLOCKED: {reason}; no repository execution attempted")
    return 2


def host_uv(argv):
    """Q5: host-side uv never reads uv settings from the audited pyproject.toml."""
    if contract.enabled():
        contract.require("Q5", "--no-config" in argv, "host uv ran without --no-config")
    return checked(argv, timeout=600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--python-version", choices=("3.11", "3.13"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    tools = Path(__file__).resolve().parent
    # Docker reads --mount and --secret values as comma-separated fields, so a comma in
    # a folder that is mounted, or that holds the exported or copied CA bundle, would
    # split one: refused here, before anything runs (ca_bundle copies a CA file whose
    # own path has one). Docker parses those values as CSV, so a double quote or a line
    # break breaks them too.
    for label, folder in (("--output", output), ("The runner folder", tools)):
        if any(mark in str(folder) for mark in CSV_MARKS):
            raise SystemExit(
                f"{label} must not contain a comma, a double quote or a line break: {folder}"
            )
    # A used folder would keep an earlier runner.json that a failed run never replaces.
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise SystemExit(f"--output must be a new or empty folder: {output}")
    output.mkdir(parents=True, exist_ok=True)
    results = output / "results"
    results.mkdir(exist_ok=True)
    if not host_tool("docker"):
        return blocked(results, "Docker executable unavailable")
    env = os.environ.copy()
    env["AUDIT_HOST_CANARY"] = "NON_SECRET_HOST_ENV_FIXTURE"
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        env.pop(key, None)
    # Docker Desktop on Windows can be switched to Windows containers; the audit
    # image and every boundary check need a Linux daemon.
    try:
        daemon = checked(docker_command("info", "--format", "{{.OSType}}"), env=env, timeout=60)
    except (RuntimeError, subprocess.TimeoutExpired):
        return blocked(results, "Docker daemon unreachable")
    if daemon != "linux":
        return blocked(results, "Docker daemon does not run Linux containers")
    staged = output / "verified-source"
    records = stage_source(args.source.resolve(), staged, args.expected_sha)
    write_text(
        results / "source-identity.json",
        json.dumps({"sha": args.expected_sha, "files": records}, indent=2),
    )
    context = output / "build-context"
    context.mkdir()
    metadata = context / "metadata"
    for relative in (
        "pyproject.toml",
        "uv.lock",
        "data-pipeline/data-preparation/pyproject.toml",
        "data-mining-framework/pyproject.toml",
        "strategy-evaluation/pyproject.toml",
    ):
        destination = metadata / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged / relative, destination)
    uv = host_tool("uv")
    if not uv:
        raise RuntimeError("Trusted setup requires uv for metadata-only export")
    # --no-config: uv settings in the audited pyproject.toml (such as cache-dir)
    # must not steer host-side uv. Path sources are still read (see README).
    common = [
        "--no-config",
        "--offline",
        "--no-build",
        "--no-python-downloads",
        "--python",
        sys.executable,
        "--directory",
        str(metadata),
    ]
    host_uv([uv, "lock", "--check", *common])
    host_uv(
        [
            uv,
            "export",
            "--frozen",
            "--no-emit-workspace",
            *common,
            "--output-file",
            str(context / "requirements.txt"),
        ]
    )
    shutil.copyfile(tools / "Dockerfile", context / "Dockerfile")
    shutil.copyfile(tools / "build-requirements.txt", context / "build-requirements.txt")
    base = f"python:{args.python_version}-slim-bookworm"
    checked(docker_command("pull", base), env=env, timeout=900)
    digest = checked(
        docker_command("image", "inspect", base, "--format", "{{index .RepoDigests 0}}"),
        env=env,
        timeout=60,
    )
    build = docker_command(
        "build",
        "--pull=false",
        "--build-arg",
        f"BASE_IMAGE={digest}",
        "--iidfile",
        str(output / "image-id"),
        "--secret",
        f"id=proxy_ca,src={ca_bundle(output)}",
        str(context),
    )
    built = run_captured(build, env=env, text=True, encoding="utf-8", errors="replace", timeout=900)
    write_text(results / "image-build.log", built.stdout + built.stderr)
    if built.returncode:
        # Build output can echo audited metadata; keep it to one escaped line.
        log_line("AUDIT_IMAGE_BUILD_LOG", built.stdout + built.stderr)
    built.check_returncode()
    image = (output / "image-id").read_text(encoding="ascii").strip()
    work = output / "work"
    work.mkdir()
    work.chmod(0o777)
    # Generated outside-input fixture; never a real credential.
    sentinel = output / "host-only-sentinel"
    write_text(sentinel, "NON_SECRET_OUTSIDE_FIXTURE")
    uid, gid = container_user()
    command = execution_command(image, staged, work, tools, sentinel, os.getpid(), uid, gid)
    container_name = "invest-audit-" + uuid.uuid4().hex
    command[3:3] = ["--name", container_name]
    write_text(
        results / "launch.json",
        json.dumps(
            {
                "base_digest": digest,
                "image_id": image,
                "command": command,
                "sha": args.expected_sha,
            },
            indent=2,
        ),
    )
    removed = False
    try:
        execution, termination = run_bounded(command, env=env)
    finally:
        removed = remove_container(container_name, env)
    if contract.enabled():
        contract.require("P1", removed, "collection started before the container was removed")
    write_text(results / "execution.log", execution.stdout + execution.stderr)
    # Container text is data, never a GitHub workflow command. Only the host's
    # private, validated snapshot can supply evidence or uploaded output.
    log_line("AUDIT_CONTAINER_STDOUT", execution.stdout)
    log_line("AUDIT_CONTAINER_STDERR", execution.stderr)
    collection = collect_workload(work, results)
    write_text(
        results / "runner.json",
        json.dumps(
            {
                "exit": execution.returncode,
                "collection_status": collection["status"],
                "termination_reason": termination,
                "image_id": image,
                "sha": args.expected_sha,
            },
            indent=2,
        ),
    )
    # The run fails when either the container or the collection did (README, verdict).
    print(
        f"Container audit exited {execution.returncode}; "
        f"collection {collection['status']}; evidence: {results}"
    )
    return execution.returncode or int(collection["status"] != "collected")


def report_host_error(error):
    """Host errors can quote audited names; print them as one JSON-escaped line."""
    log_line("AUDIT_RUNNER_ERROR", "".join(traceback.format_exception(error)), sys.stderr)


if __name__ == "__main__":
    # A path the console code page cannot encode (a Windows pipe's default) must not
    # turn a finished audit into exit 1 at its last print.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    try:
        status = main()
    except Exception as error:
        report_host_error(error)
        status = 1
    raise SystemExit(status)
