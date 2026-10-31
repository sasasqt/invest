"""Prepare a container-only audit on a Docker-capable disposable runner.

The host performs metadata reads and image setup only. Repository code runs only
in the final container, with no network, publishing credentials or host home mount.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def checked(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def execution_command(image, source, output, tools, sentinel, host_pid, uid, gid):
    if uid <= 0 or gid < 0:
        raise ValueError("Container execution requires an unprivileged UID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Execution requires a recorded immutable image ID")
    command = [
        "docker",
        "--host=unix:///var/run/docker.sock",
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
    ]
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


def stage_source(source, staged, expected_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Expected revision must be a full Git SHA")
    actual = checked(["git", "-C", str(source), "rev-parse", "HEAD"])
    if actual != expected_sha:
        raise ValueError("Source HEAD differs from the expected revision")
    staged.mkdir()
    listing = subprocess.check_output(["git", "-C", str(source), "ls-tree", "-rz", "HEAD"])
    records = []
    for item in listing.split(b"\0"):
        if not item:
            continue
        header, path = item.split(b"\t", 1)
        mode, kind, digest = header.decode().split()
        relative = Path(path.decode())
        if (
            mode not in ("100644", "100755")
            or kind != "blob"
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError("Only ordinary tracked files are allowed in the source fixture")
        original = source / relative
        if original.is_symlink() or not original.resolve().is_relative_to(source.resolve()):
            raise ValueError("Source fixture escapes its root")
        payload = original.read_bytes()
        observed = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        if observed != digest:
            raise ValueError(f"Dirty/mismatched source blob: {relative}")
        destination = staged / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        destination.chmod(0o755 if mode == "100755" else 0o644)
        records.append({"path": str(relative), "git_blob": digest})
    # Keep genuine commit provenance, but never copy Git credentials, config,
    # hooks, logs, alternates or global/home files into the execution boundary.
    git_dir = Path(checked(["git", "-C", str(source), "rev-parse", "--absolute-git-dir"]))
    if (git_dir / "objects/info/alternates").exists():
        raise ValueError("Materialize Git objects locally before staging")
    (staged / ".git/objects").mkdir(parents=True)
    for path in (git_dir / "objects").rglob("*"):
        rel = path.relative_to(git_dir / "objects")
        if path.is_symlink():
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
    (staged / ".git/HEAD").write_text(expected_sha + "\n")
    (staged / ".git/config").write_text(
        "[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = true\n"
    )
    if (git_dir / "shallow").is_file():
        shallow = (git_dir / "shallow").read_text()
        if not all(re.fullmatch(r"[0-9a-f]{40}", x) for x in shallow.splitlines()):
            raise ValueError("Invalid shallow-boundary metadata")
        (staged / ".git/shallow").write_text(shallow)
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
    checked(["git", "-C", str(staged), "reset", "--mixed", expected_sha], env=env)
    return records


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
        (results / "runner.json").write_text(
            json.dumps({"status": "blocked", "reason": "Docker executable unavailable"}, indent=2)
        )
        print("BLOCKED: Docker executable unavailable; no repository execution attempted")
        return 2
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
    checked(["docker", "--host=unix:///var/run/docker.sock", "info"], env=env)
    tools = Path(__file__).resolve().parent
    staged = output / "verified-source"
    records = stage_source(args.source.resolve(), staged, args.expected_sha)
    (results / "source-identity.json").write_text(
        json.dumps({"sha": args.expected_sha, "files": records}, indent=2)
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
    common = ["--offline", "--no-build", "--no-python-downloads", "--directory", str(metadata)]
    checked([uv, "lock", "--check", *common])
    checked(
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
    checked(["docker", "--host=unix:///var/run/docker.sock", "pull", base], env=env)
    digest = checked(
        [
            "docker",
            "--host=unix:///var/run/docker.sock",
            "image",
            "inspect",
            base,
            "--format",
            "{{index .RepoDigests 0}}",
        ],
        env=env,
    )
    build = [
        "docker",
        "--host=unix:///var/run/docker.sock",
        "build",
        "--pull=false",
        "--build-arg",
        f"BASE_IMAGE={digest}",
        "--iidfile",
        str(output / "image-id"),
        "--secret",
        "id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt",
        str(context),
    ]
    built = subprocess.run(build, env=env, capture_output=True, text=True, timeout=900)
    (results / "image-build.log").write_text(built.stdout + built.stderr)
    built.check_returncode()
    image = (output / "image-id").read_text().strip()
    work = output / "work"
    work.mkdir()
    work.chmod(0o777)
    # Generated outside-input fixture; never a real credential.
    sentinel = output / "host-only-sentinel"
    sentinel.write_text("NON_SECRET_OUTSIDE_FIXTURE")
    uid, gid = os.getuid() or 65534, os.getgid() or 65534
    command = execution_command(image, staged, work, tools, sentinel, os.getpid(), uid, gid)
    (results / "launch.json").write_text(
        json.dumps(
            {
                "base_digest": digest,
                "image_id": image,
                "command": command,
                "sha": args.expected_sha,
            },
            indent=2,
        )
    )
    execution = subprocess.run(command, env=env, capture_output=True, text=True, timeout=7200)
    (results / "execution.log").write_text(execution.stdout + execution.stderr)
    if (work / "results").is_dir():
        shutil.copytree(work / "results", results / "workload")
    (results / "runner.json").write_text(
        json.dumps(
            {"exit": execution.returncode, "image_id": image, "sha": args.expected_sha}, indent=2
        )
    )
    print(f"Container audit exited {execution.returncode}; evidence: {results}")
    return execution.returncode


if __name__ == "__main__":
    raise SystemExit(main())
