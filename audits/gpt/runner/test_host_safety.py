"""Host-side safety: audited source must not steer host tools or workflow logs.

A stand-in ``docker`` (a small Python script behind an ``sh`` or ``.cmd`` launcher)
lets the real runner reach its host-side steps without a daemon, on Linux and on
Windows. Tests that need uv skip when it is not installed.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CONTRACT_CHECKS", "1")

from isolated_runner import report_host_error

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "isolated_runner.py"
FORGED = "::error title=Forged::annotation from audited input"
# The runner also parses the older form anywhere in a line, not only at its start.
LEGACY = "older ##[error title=Forged]annotation from audited input"
MEMBERS = ("data-pipeline/data-preparation", "data-mining-framework", "strategy-evaluation")
FAKE_DOCKER = """
# Stand-in for the Docker CLI: no daemon and no containers.
import os, sys

args = sys.argv[1:]
digest = "0" * 64
if "image" in args and "inspect" in args:
    print("python@sha256:" + digest)
elif "info" in args:
    if os.environ.get("FAKE_INFO_EXIT"):
        sys.stderr.write("Cannot connect to the Docker daemon. Is the docker daemon running?\\n")
        sys.exit(int(os.environ["FAKE_INFO_EXIT"]))
    print(os.environ.get("FAKE_OS_TYPE", "linux"))
elif "ls" in args and os.environ.get("FAKE_LEFTOVER"):
    print("0123456789ab")
elif "build" in args:
    if os.environ.get("FAKE_BUILD_OUTPUT"):
        print(os.environ["FAKE_BUILD_OUTPUT"])
    if "--iidfile" in args:
        with open(args[args.index("--iidfile") + 1], "w") as stream:
            stream.write("sha256:" + digest + "\\n")
    sys.exit(int(os.environ.get("FAKE_BUILD_EXIT", "0")))
elif "run" in args:
    if os.environ.get("FAKE_RUN_OUTPUT"):
        print(os.environ["FAKE_RUN_OUTPUT"])
    if os.environ.get("FAKE_RUN_RESULT"):  # one result file in the /work mount
        for value in args:
            if value.startswith("type=bind,") and ",dst=/work" in value:
                work = value.split("src=", 1)[1].split(",dst=", 1)[0]
                os.makedirs(os.path.join(work, "results"), exist_ok=True)
                with open(os.path.join(work, "results", "result.txt"), "w") as stream:
                    stream.write(os.environ["FAKE_RUN_RESULT"])
"""


def install_fake_docker(tools):
    script = tools / "fake_docker.py"
    script.write_text(FAKE_DOCKER, encoding="utf-8")
    if os.name == "nt":
        launcher = tools / "docker.cmd"
        launcher.write_text(
            f'@"{sys.executable}" "%~dp0fake_docker.py" %*\r\n', encoding="utf-8", newline=""
        )
    else:
        launcher = tools / "docker"
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        launcher.chmod(0o755)


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def commit_all(root):
    git("add", "-A", cwd=root)
    git(
        "-c",
        "user.name=Audit Fixture",
        "-c",
        "user.email=audit@example.invalid",
        "commit",
        "-qm",
        "fixture",
        cwd=root,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def quoted(text):
    """Failure messages must not forge commands in the test job's own log either."""
    return json.dumps(text).replace("#", "\\u0023")


def forged_lines(output):
    """Lines GitHub reads as commands: '::' first, or the older '##[' anywhere."""
    return [line for line in output.splitlines() if line.lstrip().startswith("::") or "##[" in line]


class HostErrorTests(unittest.TestCase):
    def test_host_error_text_is_one_escaped_line(self):
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            report_host_error(ValueError("name\n" + FORGED + "\n" + LEGACY))
        output = captured.getvalue()
        self.assertEqual(len(output.splitlines()), 1, quoted(output))
        self.assertEqual(forged_lines(output), [], quoted(output))
        self.assertIn("Forged", output)


@unittest.skipUnless(shutil.which("git"), "Git")
class HostSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        git("init", "-q", cwd=self.source)
        tools = self.root / "bin"
        tools.mkdir()
        install_fake_docker(tools)
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("UV_", "DOCKER_"))
        }
        # Keep uv's default cache and user configuration inside the test. Not
        # UV_CACHE_DIR: it would outrank the audited cache-dir under test.
        self.env["XDG_CACHE_HOME"] = str(self.root / "xdg-cache")
        self.env["XDG_CONFIG_HOME"] = str(self.root / "xdg-config")
        self.env["PATH"] = str(tools) + os.pathsep + self.env.get("PATH", "")

    def workspace(self, uv_settings=""):
        """Write a dependency-free uv workspace with the runner's metadata paths."""
        members = ", ".join(f'"{member}"' for member in MEMBERS)
        (self.source / "pyproject.toml").write_text(
            '[project]\nname = "fixture-root"\nversion = "0"\nrequires-python = ">=3.11"\n\n'
            f"[tool.uv]\npackage = false\n{uv_settings}\n"
            f"[tool.uv.workspace]\nmembers = [{members}]\n",
            encoding="utf-8",
        )
        for number, member in enumerate(MEMBERS):
            folder = self.source / member
            folder.mkdir(parents=True)
            (folder / "pyproject.toml").write_text(
                f'[project]\nname = "fixture-member-{number}"\nversion = "0"\n'
                'requires-python = ">=3.11"\n',
                encoding="utf-8",
            )
        subprocess.run(
            [
                shutil.which("uv"),
                "lock",
                "--no-config",
                "--offline",
                "--no-python-downloads",
                "--python",
                sys.executable,
                "--cache-dir",
                str(self.root / "fixture-cache"),
                "--directory",
                str(self.source),
            ],
            env=self.env,
            check=True,
            capture_output=True,
            timeout=120,
        )
        return commit_all(self.source)

    def run_runner(self, revision, cwd=None, **extra):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--source",
                str(self.source),
                "--expected-sha",
                revision,
                "--python-version",
                "3.11",
                "--output",
                str(self.root / "output"),
            ],
            env=dict(self.env, **extra),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        # Review round 6: a broken rule in the runner process ends as a host error line
        # and exit 1, which several tests expect anyway, so it must fail the test here.
        output = result.stdout + result.stderr
        self.assertNotIn("ContractViolation", output, quoted(output))
        return result

    def plant(self, name, marker):
        """A committed program that records that it ran."""
        if os.name == "nt":
            script = self.source / (name + ".cmd")
            script.write_text(f'@echo ran > "{marker}"\r\n', encoding="utf-8", newline="")
        else:
            script = self.source / name
            script.write_text(f'#!/bin/sh\necho ran > "{marker}"\n', encoding="utf-8")
            script.chmod(0o755)

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_audited_uv_settings_cannot_choose_host_write_paths(self):
        chosen = self.root / "chosen-by-audited-source"
        revision = self.workspace(f'cache-dir = "{chosen.as_posix()}"')
        self.assertFalse(chosen.exists(), "fixture setup must not create the target")
        result = self.run_runner(revision)
        exported = self.root / "output/build-context/requirements.txt"
        self.assertTrue(exported.is_file(), quoted(result.stdout + result.stderr))
        self.assertFalse(chosen.exists(), "audited [tool.uv] steered a host write")

    @unittest.skipIf(os.name == "nt", "Windows file names cannot hold a newline")
    def test_host_errors_quoting_audited_names_cannot_start_workflow_commands(self):
        name = "!a\n" + FORGED + "\n" + LEGACY
        (self.source / name).write_text("committed\n", encoding="utf-8")
        revision = commit_all(self.source)
        result = self.run_runner(revision)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not portable to Windows and Linux", output)
        self.assertEqual(forged_lines(output), [], quoted(output))

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_failed_image_build_log_cannot_start_workflow_commands(self):
        revision = self.workspace()
        result = self.run_runner(
            revision,
            FAKE_BUILD_OUTPUT="ordinary build step\n" + FORGED + "\n" + LEGACY,
            FAKE_BUILD_EXIT="1",
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ordinary build step", output)
        self.assertEqual(forged_lines(output), [], quoted(output))

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_container_output_cannot_start_workflow_commands(self):
        revision = self.workspace()
        result = self.run_runner(
            revision, FAKE_RUN_OUTPUT="ordinary container line\n" + FORGED + "\n" + LEGACY
        )
        output = result.stdout + result.stderr
        self.assertIn("AUDIT_CONTAINER_STDOUT", output)
        self.assertIn("ordinary container line", output)
        self.assertNotEqual(result.returncode, 0, "no collected results must fail the run")
        self.assertEqual(forged_lines(output), [], quoted(output))

    def test_programs_in_the_current_folder_never_run(self):
        """Review round 5: started inside the audited checkout, a committed git, uv or
        docker ran on the host. Windows (shutil.which, CreateProcess) looks in the
        current folder before PATH; POSIX does so for a relative PATH entry."""
        marker = self.root / "PLANTED-PROGRAM-RAN"
        for name in ("git", "uv", "docker"):
            self.plant(name, marker)
        revision = commit_all(self.source)
        path = self.env["PATH"]
        if os.name != "nt":
            path = os.pathsep.join([".", path])
        result = self.run_runner(revision, cwd=self.source, PATH=path)
        self.assertFalse(marker.exists(), quoted(result.stdout + result.stderr))

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_program_in_the_current_folder_never_runs_at_the_uv_step(self):
        """Review round 6: the test above stops at the missing pyproject.toml, so it
        never reaches the uv lookup."""
        marker = self.root / "PLANTED-PROGRAM-RAN"
        self.workspace()
        self.plant("uv", marker)
        revision = commit_all(self.source)
        path = self.env["PATH"]
        if os.name != "nt":
            path = os.pathsep.join([".", path])
        result = self.run_runner(revision, cwd=self.source, PATH=path)
        output = result.stdout + result.stderr
        exported = self.root / "output/build-context/requirements.txt"
        self.assertTrue(exported.is_file(), quoted(output))
        self.assertFalse(marker.exists(), quoted(output))

    def test_a_used_output_folder_is_refused_before_anything_runs(self):
        """Review round 6: a reused --output kept the earlier runner.json, so a later
        failed run still read as the earlier result."""
        stale = self.root / "output/results/runner.json"
        stale.parent.mkdir(parents=True)
        stale.write_text('{"status": "blocked", "reason": "earlier run"}', encoding="utf-8")
        result = self.run_runner("0" * 40)
        self.assertEqual(result.returncode, 1, quoted(result.stdout + result.stderr))
        self.assertIn("--output must be a new or empty folder", result.stderr)
        self.assertEqual(json.loads(stale.read_text("utf-8"))["reason"], "earlier run")
        self.assertEqual(sorted(p.name for p in (self.root / "output").iterdir()), ["results"])

    def test_missing_docker_blocks_before_any_source_is_read(self):
        empty = self.root / "empty-path"
        empty.mkdir()
        result = self.run_runner("0" * 40, PATH=str(empty))
        self.assertEqual(result.returncode, 2, quoted(result.stdout + result.stderr))
        report = json.loads((self.root / "output/results/runner.json").read_text("utf-8"))
        self.assertEqual(report["status"], "blocked")
        self.assertFalse((self.root / "output/verified-source").exists())

    def test_unreachable_daemon_blocks_before_any_source_is_read(self):
        """Review round 5: a CLI without a running daemon ended in exit 1 and no
        runner.json, unlike a missing CLI (blocked, exit 2)."""
        result = self.run_runner("0" * 40, FAKE_INFO_EXIT="1")
        self.assertEqual(result.returncode, 2, quoted(result.stdout + result.stderr))
        report = json.loads((self.root / "output/results/runner.json").read_text("utf-8"))
        self.assertEqual(
            (report["status"], report["reason"]), ("blocked", "Docker daemon unreachable")
        )
        self.assertFalse((self.root / "output/verified-source").exists())

    def test_daemon_without_linux_containers_blocks(self):
        result = self.run_runner("0" * 40, FAKE_OS_TYPE="windows")
        self.assertEqual(result.returncode, 2, quoted(result.stdout + result.stderr))
        report = json.loads((self.root / "output/results/runner.json").read_text("utf-8"))
        self.assertEqual(report["reason"], "Docker daemon does not run Linux containers")

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_unverified_container_removal_blocks_collection(self):
        """P1: no collection while Docker still lists the container."""
        revision = self.workspace()
        result = self.run_runner(revision, FAKE_LEFTOVER="1")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, quoted(output))
        self.assertIn("removal unverified", output)
        self.assertFalse((self.root / "output/results/collection.json").exists())
        self.assertEqual(forged_lines(output), [], quoted(output))

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_a_finished_audit_keeps_its_exit_with_an_output_path_outside_the_code_page(self):
        """Review round 7: Windows writes a redirected stdout in the ANSI code page, so
        the last print of an --output path outside it raised, and an audit that
        runner.json records as collected with exit 0 ended with exit 1."""
        revision = self.workspace()
        output = self.root / "\u0141\u00f3d\u017a" / "output"
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--source",
                str(self.source),
                "--expected-sha",
                revision,
                "--python-version",
                "3.11",
                "--output",
                str(output),
            ],
            env=dict(self.env, PYTHONIOENCODING="cp1252", FAKE_RUN_RESULT="ok\n"),
            capture_output=True,
            timeout=300,
        )
        text = (result.stdout + result.stderr).decode("ascii", "replace")
        self.assertNotIn("ContractViolation", text, quoted(text))
        report = json.loads((output / "results/runner.json").read_text("utf-8"))
        self.assertEqual((report["exit"], report["collection_status"]), (0, "collected"))
        self.assertEqual(result.returncode, 0, quoted(text))
        self.assertNotIn("AUDIT_RUNNER_ERROR", text, quoted(text))


class DockerfileTests(unittest.TestCase):
    def test_no_unpinned_frontend_image(self):
        """A '# syntax=' directive makes BuildKit fetch and run that image."""
        for line in (HERE / "Dockerfile").read_text(encoding="utf-8").splitlines():
            directive = "".join(line.split()).lower()
            if directive.startswith("#syntax="):
                self.assertIn("@sha256:", directive, "pin the frontend image by digest")


class WorkflowTests(unittest.TestCase):
    def test_every_evidence_upload_keeps_hidden_files(self):
        """Review round 7: upload-artifact (v4.4.0 and later) leaves out names that
        start with a dot unless told otherwise, so a collected `.name` listed in
        collection.json with its SHA-256 would be missing from the uploaded evidence."""
        workflow = HERE.parents[2] / ".github/workflows/audit-runtime.yml"
        steps = workflow.read_text(encoding="utf-8").split("\n      - ")
        uploads = [step for step in steps if "actions/upload-artifact@" in step]
        self.assertTrue(uploads, "no upload step found")
        for step in uploads:
            with self.subTest(step=step.splitlines()[0]):
                self.assertIn("include-hidden-files: true", step)


if __name__ == "__main__":
    unittest.main()
