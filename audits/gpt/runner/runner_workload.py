"""Offline workload, invoked only by isolated_runner.py inside its container."""

import argparse
import hashlib
import json
import os
import platform
import resource
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

VOLATILE_KEYS = {"created_at", "recorded_at", "retrieved_at", "created_utc"}


def semantic_hash(directory):
    directory = Path(directory)

    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in VOLATILE_KEYS}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):
            return value.replace(str(directory), "$RUN")
        return value

    records = []
    figures = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix == ".json":
            payload = json.dumps(clean(json.loads(path.read_text())), sort_keys=True).encode()
        elif path.suffix == ".jsonl":
            payload = json.dumps(
                [clean(json.loads(line)) for line in path.read_text().splitlines() if line.strip()],
                sort_keys=True,
            ).encode()
        elif path.suffix == ".csv":
            payload = path.read_bytes()
        elif path.suffix == ".png":
            if not path.stat().st_size:
                raise ValueError("Empty figure")
            figures.append(str(path.relative_to(directory)))
            continue
        else:
            continue
        records.append((str(path.relative_to(directory)), hashlib.sha256(payload).hexdigest()))
    if not records or not figures:
        raise ValueError("Workflow produced no semantic records or figures")
    return hashlib.sha256(json.dumps([records, figures]).encode()).hexdigest()


def prove_boundary(sentinel, host_pid, results):
    status = Path("/proc/self/status").read_text()
    no_new_privs = next(
        line.split()[1] for line in status.splitlines() if line.startswith("NoNewPrivs:")
    )
    capabilities = next(
        line.split()[1] for line in status.splitlines() if line.startswith("CapEff:")
    )
    checks = {
        "unprivileged_uid": os.getuid() != 0,
        "no_new_privileges": no_new_privs == "1",
        "no_capabilities": int(capabilities, 16) == 0,
        "outside_fixture_absent": not Path(sentinel).exists(),
        "host_process_not_visible": not Path(f"/proc/{host_pid}/environ").exists(),
        "host_canary_env_absent": "AUDIT_HOST_CANARY" not in os.environ,
        "container_socket_absent": not Path("/var/run/docker.sock").exists(),
        "source_readable": Path("/input/pyproject.toml").is_file(),
    }
    try:
        Path("/input/.audit-write-probe").write_text("harmless")
        checks["source_write_denied"] = False
    except OSError:
        checks["source_write_denied"] = True
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=1):
            checks["network_connection_denied"] = False
    except OSError:
        checks["network_connection_denied"] = True
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import os,pathlib,sys; print(int(not pathlib.Path(sys.argv[1]).exists() "
            "and 'AUDIT_HOST_CANARY' not in os.environ))",
            sentinel,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    checks["child_inherits_outside_file_and_env_denial"] = (
        child.returncode == 0 and child.stdout.strip() == "1"
    )
    fixture = results / "write-positive-control"
    fixture.write_text("allowed")
    checks["output_writable"] = fixture.read_text() == "allowed"
    fixture.unlink()
    (results / "boundary.json").write_text(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise RuntimeError("Execution boundary probe failed; no project code imported")


def execute(name, argv, cwd, results, timeout=1200, env=None):
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    log = results / f"{name}.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
        )
        timed_out = False
        try:
            status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            status = 124
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = {
        "name": name,
        "argv": argv,
        "exit": status,
        "timeout": timed_out,
        "wall_seconds": time.monotonic() - started,
        "child_cpu_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
    }
    print(json.dumps(result), flush=True)
    with (results / "validation.jsonl").open("a") as stream:
        stream.write(json.dumps(result) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinel", required=True)
    parser.add_argument("--host-pid", required=True, type=int)
    args = parser.parse_args()
    work = Path("/work")
    results = work / "results"
    results.mkdir()
    (work / "home").mkdir()
    prove_boundary(args.sentinel, args.host_pid, results)
    if execute(
        "audit-guard-tests",
        [sys.executable, "-m", "unittest", "-v", "test_guards"],
        Path("/audit"),
        results,
        timeout=60,
    )["exit"]:
        return 1
    cpu_model = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "unavailable",
    )
    limits = {}
    for key in ("memory.max", "cpu.max", "pids.max"):
        path = Path("/sys/fs/cgroup") / key
        limits[key] = path.read_text().strip() if path.is_file() else "unavailable"
    (results / "environment.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": sys.version,
                "cpu_model": cpu_model,
                "limits": limits,
                "hash_seed": os.environ.get("PYTHONHASHSEED"),
                "lock_sha256": hashlib.sha256(Path("/input/uv.lock").read_bytes()).hexdigest(),
                "parallel_benchmarks": False,
            },
            indent=2,
        )
    )
    source = work / "source"
    shutil.copytree("/input", source)
    components = ["data-pipeline/data-preparation", "data-mining-framework", "strategy-evaluation"]
    built = work / "built"
    built.mkdir()
    stage = execute(
        "build-workspace",
        [
            "/buildenv/bin/python",
            "-m",
            "pip",
            "wheel",
            "--no-index",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(built),
            *[str(source / part) for part in components],
        ],
        source,
        results,
    )
    if stage["exit"]:
        return 1
    if execute(
        "create-environment",
        [sys.executable, "-m", "venv", "--system-site-packages", "/work/env"],
        source,
        results,
    )["exit"]:
        return 1
    python = "/work/env/bin/python"
    if execute(
        "install-workspace",
        [
            python,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            *[str(path) for path in sorted(built.glob("*.whl"))],
        ],
        source,
        results,
    )["exit"]:
        return 1
    env = dict(
        os.environ,
        PATH="/work/env/bin:/usr/local/bin:/usr/bin:/bin",
        COVERAGE_FILE=str(work / "coverage-data"),
    )
    checks = [
        execute(
            "installed-graph",
            [
                python,
                "/audit/verify_installed.py",
                "--requirements",
                "/requirements.txt",
                "--workspace-prefix",
                "/work/env/",
            ],
            source,
            results,
            env=env,
        )
    ]
    commands = [
        ("format", [python, "-m", "ruff", "format", "--check", "."]),
        ("lint", [python, "-m", "ruff", "check", "."]),
        ("types", [python, "-m", "mypy", *[str(source / x / "src") for x in components]]),
        (
            "tests",
            [
                python,
                "-m",
                "pytest",
                "--cov=invest_data",
                "--cov=invest_mining",
                "--cov=invest_evaluation",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-report=json:/work/results/coverage.json",
                "--durations=25",
            ],
        ),
        ("links", [python, "scripts/check_markdown_links.py"]),
    ]
    for name, argv in commands:
        checks.append(execute(name, argv, source, results, env=env))
    for cli in ("invest-data", "invest-mine", "invest-eval"):
        checks.append(
            execute("cli-" + cli, ["/work/env/bin/" + cli, "--help"], work, results, env=env)
        )
    if sys.version_info[:2] == (3, 11):
        repeat_env = dict(env, PYTHONHASHSEED="12345")
        checks.append(
            execute("hash-seed-repeat", [python, "-m", "pytest"], source, results, env=repeat_env)
        )
        for component in components:
            name = component.split("/")[-1]
            isolated = work / ("independent-" + name)
            setup = execute(
                name + "-venv", [sys.executable, "-m", "venv", str(isolated)], work, results
            )
            checks.append(setup)
            if setup["exit"]:
                continue
            interpreter = str(isolated / "bin/python")
            package = {
                components[0]: "invest_data",
                components[1]: "invest_mining",
                components[2]: "invest_evaluation",
            }[component]
            chosen = sorted(
                {
                    *[str(x) for x in built.glob("invest_data-*.whl")],
                    *[str(x) for x in built.glob(package + "-*.whl")],
                }
            )
            install = execute(
                name + "-install",
                [
                    interpreter,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links=/wheelhouse",
                    *chosen,
                    "pytest",
                ],
                work,
                results,
            )
            checks.append(install)
            if install["exit"]:
                continue
            if component == components[2]:
                checks.append(
                    execute(
                        "evaluation-independent-import",
                        [
                            interpreter,
                            "-c",
                            "import importlib.util as u; "
                            "assert u.find_spec('invest_mining') is None",
                        ],
                        work,
                        results,
                    )
                )
            checks.append(
                execute(
                    name + "-tests",
                    [
                        interpreter,
                        "-m",
                        "pytest",
                        "-p",
                        "no:cacheprovider",
                        str(source / component / "tests"),
                    ],
                    work,
                    results,
                )
            )
    # Run a small workflow even when unrelated repository tests are red. Its
    # status stays separate; timing samples require that workflow to succeed.
    case_env = dict(env, INSTRUMENTS="20", DAYS="300", TRIALS="20")
    samples = []
    reference = None
    for repetition in range(8):
        destination = work / "workflow-cases" / f"S-{repetition}"
        sample = execute(
            f"synth-S-{repetition}",
            ["bash", str(source / "scripts/synthetic_workflow.sh"), str(destination)],
            source,
            results,
            timeout=60,
            env=case_env,
        )
        sample.update(
            {
                "case": "synth-S",
                "repetition": repetition,
                "warmup": repetition == 0,
                "instruments": 20,
                "sessions": 300,
                "trials": 20,
            }
        )
        if sample["exit"] == 0:
            try:
                observed = semantic_hash(destination)
                reference = reference or observed
                sample.update(
                    {"semantic_hash": observed, "correctness_gate": observed == reference}
                )
                sample["output_bytes"] = sum(
                    p.stat().st_size for p in destination.rglob("*") if p.is_file()
                )
            except (ValueError, OSError) as exc:
                sample.update({"correctness_gate": False, "reason": str(exc)})
        else:
            sample["correctness_gate"] = False
        samples.append(sample)
        with (results / "benchmark-raw.jsonl").open("a") as stream:
            stream.write(json.dumps(sample) + "\n")
        if not sample["correctness_gate"]:
            break
    valid = [x["wall_seconds"] for x in samples if not x["warmup"] and x["correctness_gate"]]
    (results / "benchmark-summary.json").write_text(
        json.dumps(
            {
                "case": "synth-S",
                "valid_measured_samples": len(valid),
                "median_seconds": statistics.median(valid) if len(valid) == 7 else None,
                "min_seconds": min(valid) if valid else None,
                "max_seconds": max(valid) if valid else None,
                "comparison_baseline": None,
                "regression_claim": "unavailable",
                "memory_peak": "not measured",
                "scope": "subprocess wall/CPU, startup included; hashing excluded",
                "test_failures_retained": [x["name"] for x in checks if x["exit"]],
            },
            indent=2,
        )
    )
    return int(any(x["exit"] for x in checks) or len(valid) != 7)


if __name__ == "__main__":
    raise SystemExit(main())
