"""Host-side safety: audited source must not steer host tools or workflow logs.

A stand-in ``docker`` (a small Python script behind an ``sh`` or ``.cmd`` launcher)
lets the real runner reach its host-side steps without a daemon, on Linux and on
Windows. Tests that need uv skip when it is not installed.
"""

import contextlib
import fnmatch
import glob
import http.server
import io
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

os.environ.setdefault("CONTRACT_CHECKS", "1")

from isolated_runner import report_host_error
from output_collection import collect_workload

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


def upload_path_lines(step):
    """The pattern lines of an upload step's `path:` input (one line, or a `|` block);
    @actions/glob skips lines that start with `#`."""
    lines = step.splitlines()
    for number, line in enumerate(lines):
        key, _, value = line.strip().partition(":")
        if key == "path" and _:
            if value.strip() != "|":
                return [value.strip()]
            indent = len(line) - len(line.lstrip())
            block = []
            for item in lines[number + 1 :]:
                if item.strip() and len(item) - len(item.lstrip()) <= indent:
                    break
                if item.strip() and not item.strip().startswith("#"):
                    block.append(item.strip())
            return block
    raise AssertionError("upload step without path")


def upload_setting(step, key):
    """The value of one `with:` key of an upload step, without a trailing YAML comment."""
    for line in step.splitlines():
        name, colon, value = line.strip().partition(":")
        if colon and name == key:
            return value.split(" #")[0].strip()
    return None


def upload_patterns(lines):
    """(negate, pattern) for each `path:` line, as @actions/glob reads it: every leading
    `!` toggles negation and the text after it is trimmed, so `!!x` includes x."""
    patterns = []
    for line in lines:
        negate, pattern = False, line.strip()
        while pattern.startswith("!"):
            negate, pattern = not negate, pattern[1:].strip()
        patterns.append((negate, pattern))
    return patterns


def upload_root(test, lines):
    """The one include line: a plain folder, so the emulator below sees all it takes."""
    includes = [pattern for negate, pattern in upload_patterns(lines) if not negate]
    test.assertEqual(len(includes), 1, f"one evidence folder per upload: {includes}")
    test.assertFalse(set("*?[") & set(includes[0]), f"a plain folder: {includes[0]}")
    test.assertTrue(includes[0].endswith("/results"), f"the evidence folder: {includes[0]}")
    return includes


def covered(parts, pieces):
    """`*` stays within one path segment, `**` spans zero or more (dot: true); an
    exclude that matches a folder also covers everything in it (implicitDescendants).
    minimatch reads `[^...]` as `[!...]`; a trailing `/` matches folders only."""
    if not pieces:
        return True
    if pieces[0] == "**":
        return any(covered(parts[skip:], pieces[1:]) for skip in range(len(parts) + 1))
    piece = pieces[0].replace("[^", "[!")
    return bool(parts) and fnmatch.fnmatchcase(parts[0], piece) and covered(parts[1:], pieces[1:])


def upload_takes(path, patterns):
    """@actions/glob: does the upload take ``path``? It folds the patterns in order: an
    include adds what it matches and an exclude removes only what an earlier line
    added (internal-pattern-helper `match`)."""
    taken = False
    for negate, pattern in patterns:
        pieces = (pattern[:-1] + "/*/**" if pattern.endswith("/") else pattern).split("/")
        if covered(path.split("/"), pieces):
            taken = not negate
    return taken


def upload_visible(path, root, step):
    """upload-artifact leaves out every name that starts with a dot below its search
    root unless include-hidden-files is true."""
    hidden = any(part.startswith(".") for part in path.relative_to(root).parts)
    return not hidden or upload_setting(step, "include-hidden-files") == "true"


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
    def test_the_last_line_names_the_collection_as_well_as_the_exit(self):
        """Review round 10: a container that exited 0 with nothing collected ended the
        log with "Container audit exited 0", and the README called the exit in
        runner.json the verdict, although the run itself fails (exit 1)."""
        revision = self.workspace()
        result = self.run_runner(revision)
        record = json.loads((self.root / "output/results/runner.json").read_text("utf-8"))
        self.assertEqual((record["exit"], record["collection_status"]), (0, "rejected"))
        self.assertEqual(result.returncode, 1)
        self.assertTrue(
            result.stdout.splitlines()[-1].startswith(
                "Container audit exited 0; collection rejected; evidence: "
            ),
            quoted(result.stdout),
        )

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


@unittest.skipUnless(
    os.name == "posix" and hasattr(socket, "AF_UNIX") and shutil.which("docker"),
    "needs a Docker CLI and Unix sockets",
)
class DockerCliTests(unittest.TestCase):
    def test_no_proxy_from_the_cli_config_reaches_the_container(self):
        """Review round 9: the real Docker CLI adds every proxy that its config.json
        names (a proxy URL can hold a password) unless the run sets the variable, and
        FTP_PROXY was not set. A stand-in daemon on a Unix socket records the create
        request the CLI sends and refuses it, so no container is made."""
        import isolated_runner

        seen = []

        class Daemon(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def reply(self, code, body):
                data = body.encode()
                self.send_response(code)
                self.send_header("Api-Version", "1.51")
                self.send_header("OSType", "linux")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)

            def do_HEAD(self):
                self.reply(200, "OK")

            def do_GET(self):
                self.reply(200 if self.path.endswith("/_ping") else 404, "OK")

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if "/containers/create" in self.path:
                    seen.append(json.loads(body or b"{}"))
                self.reply(500, json.dumps({"message": "stand-in daemon: refused"}))

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            server = Server(str(root / "d.sock"), Daemon)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            proxy = "http://user:NOT_A_SECRET@proxy.invalid:1"
            config = root / "dockercfg"
            config.mkdir()
            (config / "config.json").write_text(
                json.dumps(
                    {
                        "proxies": {
                            "default": {
                                "httpProxy": proxy,
                                "httpsProxy": proxy,
                                "ftpProxy": proxy,
                                "allProxy": proxy,
                                "noProxy": "proxy.invalid",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            for name in ("src", "tools", "out"):
                (root / name).mkdir()
            endpoint = isolated_runner.DOCKER_ENDPOINT
            isolated_runner.DOCKER_ENDPOINT = f"unix://{root / 'd.sock'}"
            try:
                command = isolated_runner.execution_command(
                    "sha256:" + "0" * 64,
                    root / "src",
                    root / "out",
                    root / "tools",
                    None,
                    None,
                    1000,
                    1000,
                )
            finally:
                isolated_runner.DOCKER_ENDPOINT = endpoint
            env = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}
            env["DOCKER_CONFIG"] = str(config)
            # Control (review round 10): the same command without the runner's own proxy
            # entries must receive the config's proxies, or this CLI applies none and the
            # check below proves nothing (the runner's empty entries alone would pass it).
            names = [f"{name}_proxy" for name in ("http", "https", "ftp", "all", "no")]
            names += [name.upper() for name in names]
            own = {f"{name}=" for name in names}
            control = [
                value
                for index, value in enumerate(command)
                if value not in own and not (value == "--env" and command[index + 1] in own)
            ]
            done = [
                subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
                for argv in (control, command)
            ]
        self.assertEqual(len(seen), 2, f"create requests missing: {done[-1].stderr}")
        values = {"no_proxy": "proxy.invalid", "NO_PROXY": "proxy.invalid"}
        applied = set(seen[0].get("Env") or [])
        expected = {f"{name}={values.get(name, proxy)}" for name in names}
        self.assertEqual(expected - applied, set(), "this CLI applies no config.json proxy")
        leaked = [item for item in seen[1].get("Env") or [] if "proxy" in item.lower()]
        self.assertEqual([item for item in leaked if not item.endswith("=")], [])


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
                self.assertEqual(upload_setting(step, "include-hidden-files"), "true")

    def test_no_evidence_upload_takes_an_unfinished_snapshot(self):
        """Review round 8: collect_results builds its snapshot in a hidden `.collect-*`
        folder beside its destination and renames it only once the whole tree passed.
        A host process killed in between (job cancelled or timed out) leaves that
        folder, the `if: always()` uploads still run, and with include-hidden-files
        they would publish container output that was never validated as a whole."""
        workflow = HERE.parents[2] / ".github/workflows/audit-runtime.yml"
        steps = workflow.read_text(encoding="utf-8").split("\n      - ")
        uploads = [step for step in steps if "actions/upload-artifact@" in step]
        self.assertTrue(uploads, "no upload step found")
        child = (
            "import os, signal, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import output_collection as oc\n"
            "real = oc.copy_opened\n"
            "def copy_then_die(*args, **kwargs):\n"
            "    real(*args, **kwargs)\n"
            "    os.kill(os.getpid(), signal.SIGTERM)  # abrupt on POSIX and Windows\n"
            "oc.copy_opened = copy_then_die\n"
            "oc.collect_workload(sys.argv[2], sys.argv[3])\n"
        )
        for step in uploads:
            with self.subTest(step=step.splitlines()[0]), tempfile.TemporaryDirectory() as temp:
                runner_temp = Path(temp)

                def expand(line, root):
                    return (
                        line.replace("${{ runner.temp }}", root)
                        .replace("${{ matrix.python }}", "3.11")
                        .replace("${{ matrix.kind }}", "audited")
                    )

                lines = upload_path_lines(step)
                root = runner_temp.as_posix()
                includes = [expand(line, root) for line in upload_root(self, lines)]
                patterns = [
                    (negate, expand(pattern, glob.escape(root)))
                    for negate, pattern in upload_patterns(lines)
                ]
                results = Path(includes[0])
                # collection_checks.py collects each case into a folder of its own
                sink = results / "ordinary" if "name: collection-" in step else results
                sink.mkdir(parents=True)
                folder = runner_temp / "work" / "results"
                folder.mkdir(parents=True)
                (folder / "boundary.json").write_text("{not json", encoding="utf-8")
                killed = subprocess.run(
                    [sys.executable, "-c", child, str(HERE), str(runner_temp / "work"), str(sink)],
                    capture_output=True,
                    timeout=120,
                )
                self.assertNotEqual(killed.returncode, 0, "the collection was not interrupted")
                left = [path for path in sink.iterdir() if path.name.startswith(".collect-")]
                self.assertTrue(left, "no unfinished snapshot to test with")
                taken = [
                    path.relative_to(results).as_posix()
                    for path in results.rglob("*")
                    if path.is_file()
                    and upload_takes(path.as_posix(), patterns)
                    and upload_visible(path, results, step)
                ]
                self.assertEqual(taken, [], "the upload would take an unfinished snapshot")

    def test_every_evidence_upload_takes_every_collected_file(self):
        """Review round 9: W4 also keeps names that start with a dot, but an exclude that
        dropped them (`!.../results/workload/.*`) passed both tests above. A finished
        collection, with dot names and a name shaped like a snapshot's, must reach the
        artifact whole: every file collection.json lists, and collection.json itself."""
        workflow = HERE.parents[2] / ".github/workflows/audit-runtime.yml"
        steps = workflow.read_text(encoding="utf-8").split("\n      - ")
        uploads = [step for step in steps if "actions/upload-artifact@" in step]
        self.assertTrue(uploads, "no upload step found")
        for step in uploads:
            with self.subTest(step=step.splitlines()[0]), tempfile.TemporaryDirectory() as temp:
                runner_temp = Path(temp)

                def expand(line, root):
                    return (
                        line.replace("${{ runner.temp }}", root)
                        .replace("${{ matrix.python }}", "3.11")
                        .replace("${{ matrix.kind }}", "audited")
                    )

                lines = upload_path_lines(step)
                root = runner_temp.as_posix()
                includes = [expand(line, root) for line in upload_root(self, lines)]
                patterns = [
                    (negate, expand(pattern, glob.escape(root)))
                    for negate, pattern in upload_patterns(lines)
                ]
                results = Path(includes[0])
                sink = results / "ordinary" if "name: collection-" in step else results
                sink.mkdir(parents=True)
                folder = runner_temp / "work" / "results"
                (folder / "nested").mkdir(parents=True)
                for name in (".hidden", ".collect-notes", "nested/.collect-x", "plain.txt"):
                    (folder / name).write_text("evidence", encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    report = collect_workload(runner_temp / "work", sink)
                self.assertEqual(report["status"], "collected")
                listed = {(sink / "collection.json").relative_to(results).as_posix()}
                listed |= {
                    (sink / "workload" / row["path"]).relative_to(results).as_posix()
                    for row in report["files"]
                }
                taken = {
                    path.relative_to(results).as_posix()
                    for path in results.rglob("*")
                    if path.is_file()
                    and upload_takes(path.as_posix(), patterns)
                    and upload_visible(path, results, step)
                }
                self.assertEqual(taken, listed, "the upload would drop collected evidence")

    def test_upload_emulator_reads_paths_as_actions_glob_does(self):
        """Review round 10: the emulator above read `[^.]*` as a literal caret (minimatch
        negates it, so `!.../results/[^.]*` uploads only an unfinished snapshot and
        passed W4), ignored every include but the first (an added raw `work` folder
        passed), and failed a correct trailing-slash exclude or a `#` comment line."""
        cases = [
            ("/r/results/.collect-x/f", "/r/results/.collect-*", True),
            ("/r/results/.collect-x/f", "/r/results/.collect-*/", True),
            ("/r/results/.collect-x", "/r/results/.collect-*/", False),  # a file: kept
            ("/r/results/collection.json", "/r/results/[^.]*", True),
            ("/r/results/.collect-x/f", "/r/results/[^.]*", False),
            ("/r/results/workload/a/.h", "/r/results/**/.*", True),
        ]
        for path, exclude, expected in cases:
            with self.subTest(path=path, exclude=exclude):
                patterns = upload_patterns(["/r/results", "!" + exclude])
                self.assertEqual(not upload_takes(path, patterns), expected)
        step = "x\n  path: |\n    # a comment\n    /r/results\n    !/r/results/.c*\n  y: z"
        self.assertEqual(upload_path_lines(step), ["/r/results", "!/r/results/.c*"])
        self.assertEqual(upload_root(self, ["/r/results", "!/r/results/.c*"]), ["/r/results"])
        for lines in (["/r/results", "/r/work"], ["/r/results/*.json"], ["/r/other"]):
            with self.subTest(lines=lines), self.assertRaises(AssertionError):
                upload_root(self, lines)

    def test_upload_emulator_folds_lines_in_order_as_actions_glob_does(self):
        """Review round 11 (R11A-E1): @actions/glob folds the `path:` lines in order (an
        exclude removes only what an earlier line added), toggles negation for every
        leading `!` and trims the text after it, and upload-artifact keeps dot names
        only when include-hidden-files really is true. The emulator applied every
        exclude after all includes, read `!!x` as an exclude, refused `! x` and found
        the setting in a YAML comment, so four wrong workflows passed W4."""
        snapshot = "/r/results/.collect-x/f"
        late = upload_patterns(["!/r/results/.collect-*", "/r/results"])
        self.assertTrue(upload_takes(snapshot, late), "an exclude before the include")
        for exclude in ("!/r/results/.collect-*", "! /r/results/.collect-*"):
            with self.subTest(exclude=exclude):
                patterns = upload_patterns(["/r/results", exclude])
                self.assertFalse(upload_takes(snapshot, patterns))
                self.assertTrue(upload_takes("/r/results/collection.json", patterns))
        self.assertEqual(
            upload_patterns(["!!/r/work", "! /r/x", "!!!/r/y", " /r/z "]),
            [(False, "/r/work"), (True, "/r/x"), (True, "/r/y"), (False, "/r/z")],
        )
        self.assertTrue(upload_takes("/r/work/a", upload_patterns(["/r/results", "!!/r/work"])))
        self.assertEqual(upload_root(self, ["/r/results", "! /r/results/.c*"]), ["/r/results"])
        with self.assertRaises(AssertionError):
            upload_root(self, ["/r/results", "!!/r/work"])
        step = "x\n  with:\n    include-hidden-files: false # not include-hidden-files: true\n"
        self.assertEqual(upload_setting(step, "include-hidden-files"), "false")
        step = "x\n  with:\n    include-hidden-files: true # keep dot names\n"
        self.assertEqual(upload_setting(step, "include-hidden-files"), "true")
        self.assertIsNone(upload_setting("x\n  with:\n    name: y\n", "include-hidden-files"))


if __name__ == "__main__":
    unittest.main()
