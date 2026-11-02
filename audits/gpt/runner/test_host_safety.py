"""Host-side safety: audited source must not steer host tools or workflow logs.

Linux/POSIX only, like the collector: a stand-in ``docker`` shell script lets the
real runner reach its host-side steps without a daemon. Tests that need uv skip
when it is not installed.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "isolated_runner.py"
FORGED = "::error title=Forged::annotation from audited input"
MEMBERS = ("data-pipeline/data-preparation", "data-mining-framework", "strategy-evaluation")
FAKE_DOCKER = """#!/bin/sh
# Stand-in for the Docker CLI: no daemon and no containers.
case " $* " in
  *" image inspect "*) echo "python@sha256:DIGEST" ;;
  *" build "*)
    if [ -n "$FAKE_BUILD_OUTPUT" ]; then printf '%s\\n' "$FAKE_BUILD_OUTPUT"; fi
    exit "${FAKE_BUILD_EXIT:-0}" ;;
esac
exit 0
""".replace("DIGEST", "0" * 64)


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


def forged_lines(output):
    """GitHub reads a line whose first non-blank characters are '::' as a command."""
    return [line for line in output.splitlines() if line.lstrip().startswith("::")]


@unittest.skipUnless(os.name == "posix" and shutil.which("git"), "POSIX host with Git")
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
        docker = tools / "docker"
        docker.write_text(FAKE_DOCKER, encoding="utf-8")
        docker.chmod(0o755)
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("UV_", "DOCKER_"))
        }
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

    def run_runner(self, revision, **extra):
        return subprocess.run(
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
            capture_output=True,
            text=True,
            timeout=300,
        )

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_audited_uv_settings_cannot_choose_host_write_paths(self):
        chosen = self.root / "chosen-by-audited-source"
        revision = self.workspace(f'cache-dir = "{chosen.as_posix()}"')
        self.assertFalse(chosen.exists(), "fixture setup must not create the target")
        result = self.run_runner(revision)
        exported = self.root / "output/build-context/requirements.txt"
        self.assertTrue(exported.is_file(), result.stdout + result.stderr)
        self.assertFalse(chosen.exists(), "audited [tool.uv] steered a host write")

    def test_host_errors_quoting_audited_names_cannot_start_workflow_commands(self):
        name = "!a\n" + FORGED
        (self.source / name).write_text("committed\n", encoding="utf-8")
        revision = commit_all(self.source)
        (self.source / name).write_text("changed after the commit\n", encoding="utf-8")
        result = self.run_runner(revision)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Dirty/mismatched source blob", output)
        self.assertEqual(forged_lines(output), [], output)

    @unittest.skipUnless(shutil.which("uv"), "uv not installed")
    def test_failed_image_build_log_cannot_start_workflow_commands(self):
        revision = self.workspace()
        result = self.run_runner(
            revision, FAKE_BUILD_OUTPUT="ordinary build step\n" + FORGED, FAKE_BUILD_EXIT="1"
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ordinary build step", output)
        self.assertEqual(forged_lines(output), [], output)


class DockerfileTests(unittest.TestCase):
    def test_no_unpinned_frontend_image(self):
        """A '# syntax=' directive makes BuildKit fetch and run that image."""
        for line in (HERE / "Dockerfile").read_text(encoding="utf-8").splitlines():
            directive = line.replace(" ", "").lower()
            if directive.startswith("#syntax="):
                self.assertIn("@sha256:", directive, "pin the frontend image by digest")


if __name__ == "__main__":
    unittest.main()
