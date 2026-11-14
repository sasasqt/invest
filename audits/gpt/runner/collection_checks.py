"""Docker acceptance checks for hostile output; generated non-secret fixtures only."""

import argparse
import contextlib
import io
import json
import os
import sys
import uuid
from pathlib import Path

from isolated_runner import (
    checked,
    container_user,
    docker_command,
    execution_command,
    remove_container,
    run_bounded,
)
from output_collection import SUMMARY_NAMES, collect_workload

FIXTURE = r"""
import json, os, pathlib, shutil, sys
sys.path.insert(0, '/audit')
from runner_workload import prove_boundary
mode, sentinel, host_pid, outside_dir = sys.argv[1:]
work = pathlib.Path('/work')
results = work / 'results'
results.mkdir()
prove_boundary(sentinel, int(host_pid), results)
print('BOUNDARY_OK', flush=True)
(results / 'environment.json').write_text(json.dumps({'fixture': 'synthetic'}))
(results / 'benchmark-summary.json').write_text(json.dumps({'fixture': 'not a benchmark'}))
(results / 'ordinary.txt').write_text('ordinary evidence')
if mode == 'file-link':
    (results / 'escape').symlink_to(sentinel)
elif mode == 'directory-link':
    (results / 'escape').symlink_to(outside_dir, target_is_directory=True)
elif mode == 'root-link':
    shutil.rmtree(results)
    results.symlink_to(outside_dir, target_is_directory=True)
elif mode.startswith('summary-'):
    target = results / mode.removeprefix('summary-')
    target.unlink()
    target.symlink_to(sentinel)
elif mode == 'fifo':
    os.mkfifo(results / 'pipe')
elif mode == 'hard-link':
    (work / 'shared').write_text('ordinary hard-link fixture')
    os.link(work / 'shared', results / 'shared')
elif mode == 'oversize':
    with (results / 'large').open('wb') as stream:
        stream.truncate(16 * 1024 * 1024 + 1)
elif mode != 'ordinary':
    raise RuntimeError('unknown fixture')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", choices=("3.11", "3.13"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # The container probes take a host path and process ID, which name nothing inside
    # the Linux container when Docker runs in a virtual machine (Windows, macOS).
    if sys.platform != "linux":
        raise SystemExit("collection_checks.py runs on a Linux host with Docker only")
    output = args.output.resolve()
    output.mkdir(parents=True)
    evidence = output / "results"
    evidence.mkdir()
    source = output / "toy-source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname="generated-boundary-fixture"\n', encoding="utf-8"
    )
    sentinel = output / "host-only-canary"
    marker = ("NON_SECRET_CANARY_" + uuid.uuid4().hex).encode()
    sentinel.write_bytes(marker)
    outside = output / "host-only-directory"
    outside.mkdir()
    (outside / "canary").write_bytes(marker)
    env = dict(os.environ, AUDIT_HOST_CANARY="NON_SECRET_ENV_FIXTURE")
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        env.pop(key, None)
    docker = docker_command()
    base = f"python:{args.python_version}-slim-bookworm"
    checked([*docker, "pull", base], env=env, timeout=300)
    image = checked([*docker, "image", "inspect", base, "--format", "{{.Id}}"], env=env)
    digest = checked(
        [*docker, "image", "inspect", base, "--format", "{{index .RepoDigests 0}}"], env=env
    )
    rows = []
    cases = ["ordinary", "file-link", "directory-link", "root-link"]
    cases += ["summary-" + name for name in SUMMARY_NAMES]
    cases += ["fifo", "hard-link", "oversize"]
    for number, mode in enumerate(cases):
        work = output / f"work-{number}"
        work.mkdir(mode=0o777)
        work.chmod(0o777)
        target = evidence / mode
        target.mkdir()
        command = execution_command(
            image,
            source,
            work,
            Path(__file__).resolve().parent,
            sentinel,
            os.getpid(),
            *container_user(),
        )
        name = "invest-collection-check-" + uuid.uuid4().hex
        command[3:3] = ["--name", name]
        command[command.index(image) + 1 :] = [
            "python",
            "-I",
            "-c",
            FIXTURE,
            mode,
            str(sentinel),
            str(os.getpid()),
            str(outside),
        ]
        try:
            run, reason = run_bounded(command, env=env, timeout=30)
        finally:
            remove_container(name, env)
        if run.returncode or reason or "BOUNDARY_OK" not in run.stdout.splitlines():
            raise RuntimeError("Synthetic container fixture failed: " + json.dumps(mode))
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            collected = collect_workload(work, target)
        expected = "collected" if mode == "ordinary" else "rejected"
        if collected["status"] != expected:
            raise AssertionError("Unexpected collection outcome: " + json.dumps(mode))
        if marker in (run.stdout + captured.getvalue()).encode():
            raise AssertionError("Generated outside canary reached logs")
        for path in target.rglob("*"):
            if path.is_symlink():
                raise AssertionError("Unsafe link reached artifact tree")
            if path.is_file() and marker in path.read_bytes():
                raise AssertionError("Generated outside canary reached artifact tree")
        if mode == "ordinary":
            if not all(collected["summaries"]["boundary.json"].values()):
                raise AssertionError("Ordinary boundary control failed")
            if (target / "workload/ordinary.txt").read_text(
                encoding="utf-8"
            ) != "ordinary evidence":
                raise AssertionError("Ordinary output was not preserved")
        row = {
            "case": mode,
            "boundary_checks": "passed",
            "collection": expected,
            "outside_bytes_in_logs_or_artifacts": False,
            "unsafe_artifact_links": False,
        }
        rows.append(row)
        print("COLLECTION_CASE " + json.dumps(row), flush=True)
        (evidence / "acceptance.json").write_text(
            json.dumps(
                {
                    "image_id": image,
                    "base_digest": digest,
                    # False until every case passed: a failed case stops the run early.
                    "complete": len(rows) == len(cases),
                    "cases": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
