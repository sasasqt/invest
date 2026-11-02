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
SYSTEM_CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"
SERVER_AUTH = "1.3.6.1.5.5.7.3.1"


def docker_command(*args):
    """The Docker CLI, resolved on PATH once per call site, aimed at the local daemon."""
    return [shutil.which("docker") or "docker", f"--host={DOCKER_ENDPOINT}", *args]


def write_text(path, text):
    """UTF-8 with LF line ends on every host (Windows defaults to its code page and CRLF)."""
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def checked(argv, **kwargs):
    result = subprocess.run(
        argv, text=True, encoding="utf-8", errors="replace", capture_output=True, **kwargs
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(argv[0]).name} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


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
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "timeout"
                break
            reader.join(min(0.1, remaining))
        if over.is_set():
            reason = "log_limit"
    finally:
        if process.poll() is None:
            process.kill()
        status = process.wait(timeout=30)
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
    subprocess.run(
        docker_command("container", "rm", "--force", name),
        env=env,
        capture_output=True,
        timeout=30,
    )
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
    """
    for candidate in (SYSTEM_CA_BUNDLE, ssl.get_default_verify_paths().cafile):
        if candidate and Path(candidate).is_file():
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
        if "," in text:
            raise ValueError("A mount path must not contain a comma")
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
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "NO_PROXY": "",
        "http_proxy": "",
        "https_proxy": "",
        "all_proxy": "",
        "no_proxy": "",
    }.items():
        command += ["--env", f"{name}={value}"]
    command += [
        image,
        "python",
        "/audit/runner_workload.py",
        "--sentinel",
        str(sentinel),
        "--host-pid",
        str(host_pid),
    ]
    return command


def blob_digest(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


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
        if not all(portable_name(part) for part in parts):
            raise ValueError(f"Source path is not portable to Windows and Linux: {path}")
        # Windows folds case: two paths that differ only by case would overwrite each
        # other there, so both hosts refuse them.
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            kind_of = (prefix, depth == len(parts))
            if kinds.setdefault(prefix.casefold(), kind_of) != kind_of:
                raise ValueError(f"Source paths differ only by case: {path}")
        entries.append((path, mode, digest))
    return entries


def read_blobs(source, digests):
    """Read each blob from Git's object store, not from the checked-out files.

    Git on Windows checks text out with CRLF line ends, so checked-out bytes need not
    match the commit; the object store always holds the committed bytes.
    """
    request = "".join(digest + "\n" for digest in digests).encode("ascii")
    result = subprocess.run(
        ["git", "-C", str(source), "cat-file", "--batch"],
        input=request,
        capture_output=True,
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


def stage_source(source, staged, expected_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Expected revision must be a full Git SHA")
    actual = checked(["git", "-C", str(source), "rev-parse", "HEAD"], timeout=GIT_TIMEOUT)
    if actual != expected_sha:
        raise ValueError("Source HEAD differs from the expected revision")
    listing = subprocess.run(
        ["git", "-C", str(source), "ls-tree", "-rz", expected_sha],
        capture_output=True,
        check=True,
        timeout=GIT_TIMEOUT,
    ).stdout
    entries = source_entries(listing)
    staged.mkdir()
    records = []
    for (path, mode, digest), payload in zip(
        entries, read_blobs(source, [digest for _, _, digest in entries]), strict=True
    ):
        destination = staged.joinpath(*path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:  # never overwrite: a case clash fails here too
            stream.write(payload)
        destination.chmod(0o755 if mode == "100755" else 0o644)
        if contract.enabled():
            contract.require("Q4", blob_digest(destination.read_bytes()) == digest, path)
        records.append({"path": path, "git_blob": digest})
    # Keep genuine commit provenance, but never copy Git credentials, config,
    # hooks, logs, alternates or global/home files into the execution boundary.
    git_dir = Path(
        checked(["git", "-C", str(source), "rev-parse", "--absolute-git-dir"], timeout=GIT_TIMEOUT)
    )
    if (git_dir / "objects/info/alternates").exists():
        raise ValueError("Materialize Git objects locally before staging")
    (staged / ".git/objects").mkdir(parents=True)
    for path in (git_dir / "objects").rglob("*"):
        rel = path.relative_to(git_dir / "objects")
        if is_link(path.lstat()):  # symbolic links, and junctions on Windows
            raise ValueError("Symlink in Git object store")
        permitted = (
            len(rel.parts) == 2
            and re.fullmatch(r"[0-9a-f]{2}", rel.parts[0])
            and re.fullmatch(r"[0-9a-f]{38}", rel.parts[1])
        ) or (
            len(rel.parts) == 2
            and rel.parts[0] == "pack"
            and re.fullmatch(r"pack-[0-9a-f]{40}\.(pack|idx|rev)", rel.parts[1])
        )
        if path.is_file() and permitted:
            target = staged / ".git/objects" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
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
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    checked(
        ["git", "-C", str(staged), "reset", "--mixed", expected_sha], env=env, timeout=GIT_TIMEOUT
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
    output.mkdir(parents=True, exist_ok=True)
    results = output / "results"
    results.mkdir(exist_ok=True)
    if not shutil.which("docker"):
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
    daemon = checked(docker_command("info", "--format", "{{.OSType}}"), env=env, timeout=60)
    if daemon != "linux":
        return blocked(results, "Docker daemon does not run Linux containers")
    tools = Path(__file__).resolve().parent
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
    uv = shutil.which("uv")
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
    built = subprocess.run(
        build,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
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
    print(f"Container audit exited {execution.returncode}; evidence: {results}")
    return execution.returncode or int(collection["status"] != "collected")


def report_host_error(error):
    """Host errors can quote audited names; print them as one JSON-escaped line."""
    log_line("AUDIT_RUNNER_ERROR", "".join(traceback.format_exception(error)), sys.stderr)


if __name__ == "__main__":
    try:
        status = main()
    except Exception as error:
        report_host_error(error)
        status = 1
    raise SystemExit(status)
