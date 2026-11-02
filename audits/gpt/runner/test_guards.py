import copy
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CONTRACT_CHECKS", "1")

import isolated_runner
from ci_evidence import classify
from isolated_runner import (
    blob_digest,
    ca_bundle,
    checked,
    container_user,
    docker_command,
    execution_command,
    read_blobs,
    run_bounded,
    source_entries,
    stage_source,
)
from runner_workload import semantic_hash, semantic_manifest
from verify_installed import applicable_requirements, verify_versions
from verify_snapshot import SnapshotError, verify

BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"  # the empty blob


def listing(*rows):
    """Build ``git ls-tree -rz`` output from (mode, kind, path) rows."""
    return b"".join(
        f"{mode} {kind} {BLOB}\t".encode()
        + (path if isinstance(path, bytes) else path.encode())
        + b"\0"
        for mode, kind, path in rows
    )


def fixture_repository(root, files):
    source = root / "original"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    for name, payload in files.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_bytes(payload)
    subprocess.run(["git", "-C", str(source), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "core.autocrlf=false",
            "-c",
            "user.name=Audit Fixture",
            "-c",
            "user.email=audit@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    return source, revision


class SnapshotTests(unittest.TestCase):
    def test_missing_manifest_is_blocked(self):
        (self.snapshot / "snapshot.json").unlink()
        self.assertEqual(verify(self.reference, self.snapshot)["status"], "blocked")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "snapshot"
        (self.snapshot / "raw").mkdir(parents=True)
        # This is a generated toy byte fixture, not vendor data.
        self.payload = b'{"toy":true}\n'
        self.file = self.snapshot / "raw" / "AAA.json"
        self.file.write_bytes(self.payload)
        self.expected = {
            "request": {"start": "2010-01-01", "end": "2024-12-31"},
            "files": {
                "AAA": {
                    "path": "raw/AAA.json",
                    "bytes": len(self.payload),
                    "sha256": hashlib.sha256(self.payload).hexdigest(),
                }
            },
        }
        self.reference = self.root / "expected.json"
        self.save()

    def save(self):
        self.reference.write_text(json.dumps(self.expected))
        (self.snapshot / "snapshot.json").write_text(json.dumps(self.expected))

    def test_matching_fixture(self):
        result = verify(self.reference, self.snapshot)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["verified_bytes"], len(self.payload))

    def test_json_formatting_is_not_data_identity(self):
        (self.snapshot / "snapshot.json").write_text(json.dumps(self.expected, indent=4))
        self.assertEqual(verify(self.reference, self.snapshot)["status"], "verified")

    def test_missing_directory_is_blocked(self):
        self.assertEqual(verify(self.reference, self.root / "missing")["status"], "blocked")

    def test_missing_raw_file_is_blocked(self):
        self.file.unlink()
        self.assertEqual(verify(self.reference, self.snapshot)["missing"], ["raw/AAA.json"])

    def test_tampering_same_length_is_rejected(self):
        self.file.write_bytes(self.payload.replace(b"true", b"null"))
        with self.assertRaisesRegex(SnapshotError, "SHA-256"):
            verify(self.reference, self.snapshot)

    def test_wrong_size_is_rejected(self):
        self.file.write_bytes(self.payload + b"x")
        with self.assertRaisesRegex(SnapshotError, "byte count"):
            verify(self.reference, self.snapshot)

    def test_changed_request_is_rejected(self):
        different = copy.deepcopy(self.expected)
        different["request"]["start"] = "2011-01-01"
        (self.snapshot / "snapshot.json").write_text(json.dumps(different))
        with self.assertRaisesRegex(SnapshotError, "differs"):
            verify(self.reference, self.snapshot)

    def test_reserved_window_rejected_before_raw_read(self):
        self.expected["request"]["end"] = "2025-01-01"
        self.save()
        with self.assertRaisesRegex(SnapshotError, "pre-2025"):
            verify(self.reference, self.snapshot)

    def test_parent_escape_is_rejected(self):
        self.expected["files"]["AAA"]["path"] = "raw/../../outside"
        self.save()
        with self.assertRaisesRegex(SnapshotError, "Unsafe"):
            verify(self.reference, self.snapshot)

    def test_absolute_path_is_rejected(self):
        self.expected["files"]["AAA"]["path"] = "/etc/passwd"
        self.save()
        with self.assertRaisesRegex(SnapshotError, "Unsafe"):
            verify(self.reference, self.snapshot)

    def test_raw_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.write_bytes(self.payload)
        self.file.unlink()
        self.file.symlink_to(outside)
        with self.assertRaisesRegex(SnapshotError, "Symlink"):
            verify(self.reference, self.snapshot)

    def test_duplicate_manifest_key_is_rejected(self):
        (self.snapshot / "snapshot.json").write_text('{"request":{},"request":{}}')
        with self.assertRaisesRegex(SnapshotError, "Duplicate"):
            verify(self.reference, self.snapshot)


class EvidenceTests(unittest.TestCase):
    def test_queued_job_is_pending_not_fresh_execution(self):
        jobs = [self.job(started=None, status="queued", conclusion=None)]
        result = classify({"head_sha": "pinned"}, jobs, "pinned", "2026-10-31T07:40:00Z")
        item = next(x for x in result if x["name"] == "checks (3.11)")
        self.assertEqual(item["evidence"], "pending_not_started")

    def job(self, started="2026-10-31T07:40:27Z", **overrides):
        return {
            "id": 1,
            "name": "checks (3.11)",
            "started_at": started,
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 2,
            **overrides,
        }

    def test_wrong_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "revision"):
            classify({"head_sha": "other"}, [], "pinned", "2026-10-31T07:40:00Z")

    def test_copied_attempt_number_does_not_make_old_job_fresh(self):
        result = classify(
            {"head_sha": "pinned"},
            [self.job("2026-10-08T22:04:20Z")],
            "pinned",
            "2026-10-31T07:40:00Z",
        )
        self.assertEqual(
            next(x for x in result if x["name"] == "checks (3.11)")["evidence"], "historical_reused"
        )

    def test_fresh_failure_is_retained(self):
        result = classify(
            {"head_sha": "pinned"},
            [self.job(conclusion="failure")],
            "pinned",
            "2026-10-31T07:40:00Z",
        )
        item = next(x for x in result if x["name"] == "checks (3.11)")
        self.assertEqual((item["evidence"], item["conclusion"]), ("fresh", "failure"))

    def test_unrun_jobs_remain_missing(self):
        result = classify({"head_sha": "pinned"}, [], "pinned", "2026-10-31T07:40:00Z")
        self.assertEqual(len(result), 6)
        self.assertTrue(all(x["evidence"] == "missing" for x in result))

    def test_newest_job_wins_without_hiding_failure(self):
        jobs = [self.job("2026-10-08T22:04:20Z"), self.job(conclusion="failure", id=2)]
        result = classify({"head_sha": "pinned"}, jobs, "pinned", "2026-10-31T07:40:00Z")
        item = next(x for x in result if x["name"] == "checks (3.11)")
        self.assertEqual(item["job_id"], 2)
        self.assertEqual(item["conclusion"], "failure")


class RunnerContractTests(unittest.TestCase):
    def test_root_container_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, "unprivileged"):
            execution_command(
                "sha256:" + "0" * 64, "/tmp/a", "/tmp/b", "/tmp/c", "/tmp/d", 10, 0, 0
            )

    def test_offline_restricted_command(self):
        command = execution_command(
            "sha256:" + "0" * 64,
            "/tmp/source",
            "/tmp/output",
            "/tmp/tools",
            "/tmp/sentinel",
            12345,
            1000,
            1000,
        )
        for required in (
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=2g",
            "--pids-limit=256",
            "TMPDIR=/work/tmp",
        ):
            self.assertIn(required, command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("--env-file", command)
        self.assertFalse(any("AUDIT_HOST_CANARY=" in item for item in command))
        self.assertTrue(any("dst=/input,readonly" in item for item in command))
        self.assertTrue(any("dst=/audit,readonly" in item for item in command))
        self.assertFalse(any("docker.sock,dst=" in item for item in command))

    def test_mutable_image_tag_rejected(self):
        with self.assertRaisesRegex(ValueError, "immutable"):
            execution_command(
                "python:latest", "/tmp/a", "/tmp/b", "/tmp/c", "/tmp/d", 10, 1000, 1000
            )

    def test_mount_option_injection_rejected(self):
        with self.assertRaisesRegex(ValueError, "comma"):
            execution_command(
                "sha256:" + "0" * 64,
                "/tmp/a,readonly=false",
                "/tmp/b",
                "/tmp/c",
                "/tmp/d",
                10,
                1000,
                1000,
            )

    def test_genuine_revision_preserved_without_git_credential_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            (source / "example.txt").write_text("trusted toy fixture\n")
            subprocess.run(["git", "-C", str(source), "add", "example.txt"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "-c",
                    "user.name=Audit Fixture",
                    "-c",
                    "user.email=audit@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                check=True,
            )
            revision = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip()
            # A harmless fake value proves local config is not copied.
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "config",
                    "http.extraheader",
                    "X-Audit-Fake: NON_SECRET_TEST",
                ],
                check=True,
            )
            staged = root / "staged"
            records = stage_source(source, staged, revision)
            self.assertEqual(len(records), 1)
            self.assertNotIn("NON_SECRET_TEST", (staged / ".git/config").read_text())
            actual = subprocess.check_output(
                ["git", "-C", str(staged), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(actual, revision)
            dirty = subprocess.check_output(
                ["git", "-C", str(staged), "status", "--porcelain"], text=True
            )
            self.assertEqual(dirty, "")

    def test_semantic_gate_preserves_numeric_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one, two = root / "one", root / "two"
            for item in (one, two):
                item.mkdir()
                (item / "figure.png").write_bytes(b"TOY_NONEMPTY_FIGURE")
                (item / "metrics.json").write_text(
                    json.dumps({"created_at": item.name, "output": str(item), "return": 0.25})
                )
            self.assertEqual(semantic_hash(one), semantic_hash(two))
            (two / "metrics.json").write_text(
                json.dumps({"created_at": "later", "return": 0.5, "output": str(two)})
            )
            self.assertNotEqual(semantic_hash(one), semantic_hash(two))

    def test_missing_semantic_outputs_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "semantic records"):
                semantic_hash(directory)


class PortableHostTests(unittest.TestCase):
    """Host-side parts that differ between Linux and Windows (Windows port, PR #36)."""

    def test_staging_uses_committed_bytes_not_checked_out_bytes(self):
        """Git on Windows checks text out with CRLF; the old byte check failed every file."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"dir/text.txt": b"line\nnext\n"})
            (source / "dir/text.txt").write_bytes(b"line\r\nnext\r\n")  # as autocrlf would
            records = stage_source(source, root / "staged", revision)
            self.assertEqual((root / "staged/dir/text.txt").read_bytes(), b"line\nnext\n")
            self.assertEqual(
                records, [{"path": "dir/text.txt", "git_blob": blob_digest(b"line\nnext\n")}]
            )
            self.assertEqual((root / "staged/.git/HEAD").read_bytes(), revision.encode() + b"\n")

    def test_ordinary_paths_are_listed_in_order(self):
        rows = [("100644", "blob", "README.md"), ("100755", "blob", "tools/run.sh")]
        self.assertEqual(
            source_entries(listing(*rows)),
            [("README.md", "100644", BLOB), ("tools/run.sh", "100755", BLOB)],
        )

    def test_paths_other_hosts_would_read_differently_are_refused(self):
        paths = (
            "CON",
            "dir/nul.txt",
            "trailing.",
            "dir./file",
            "a:b",
            "back\\slash",
            "a\nb",
            "a\tb",
        )
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "not portable"):
                    source_entries(listing(("100644", "blob", path)))
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            source_entries(listing(("100644", "blob", b"bad-\xff")))

    def test_links_and_submodules_are_refused(self):
        for mode, kind in (("120000", "blob"), ("160000", "commit"), ("100664", "blob")):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, "ordinary tracked files"):
                    source_entries(listing((mode, kind, "item")))

    def test_case_clashes_are_refused(self):
        for pair in (("Readme", "README"), ("a", "A/b"), ("Dir/x", "dir/y")):
            with self.subTest(pair=pair):
                rows = [("100644", "blob", path) for path in pair]
                with self.assertRaisesRegex(ValueError, "clash when case is ignored"):
                    source_entries(listing(*rows))
        rows = [("100644", "blob", "dir/x"), ("100644", "blob", "dir/y")]
        self.assertEqual(len(source_entries(listing(*rows))), 2)

    def test_missing_object_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _ = fixture_repository(Path(directory), {"a.txt": b"a\n"})
            with self.assertRaisesRegex(ValueError, "missing or not a blob"):
                read_blobs(source, ["1" * 40])
            self.assertEqual(read_blobs(source, [blob_digest(b"a\n")]), [b"a\n"])
            self.assertEqual(read_blobs(source, []), [])

    def test_docker_always_targets_the_local_daemon(self):
        command = docker_command("info")
        expected = (
            "npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock"
        )
        self.assertEqual(command[1:], [f"--host={expected}", "info"])

    def test_container_user_is_never_root(self):
        uid, gid = container_user()
        self.assertGreater(uid, 0)
        self.assertGreater(gid, 0)
        if os.name == "nt":
            self.assertEqual((uid, gid), (65534, 65534))

    def test_ca_bundle_prefers_the_system_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "system.pem"
            bundle.write_text("-----BEGIN CERTIFICATE-----\n", encoding="ascii")
            with patch.object(isolated_runner, "SYSTEM_CA_BUNDLE", str(bundle)):
                self.assertEqual(ca_bundle(Path(directory)), bundle)

    def test_ca_bundle_without_any_source(self):
        paths = isolated_runner.ssl.DefaultVerifyPaths(None, None, None, None, None, None)
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(isolated_runner, "SYSTEM_CA_BUNDLE", str(Path(directory) / "none")),
                patch.object(isolated_runner.ssl, "get_default_verify_paths", return_value=paths),
            ):
                if os.name == "nt":  # the Windows certificate store is exported as PEM
                    exported = ca_bundle(Path(directory))
                    text = exported.read_text(encoding="ascii")
                    self.assertTrue(text.startswith("-----BEGIN CERTIFICATE-----\n"))
                    self.assertNotIn("\r", text)
                else:
                    with self.assertRaisesRegex(RuntimeError, "No CA bundle"):
                        ca_bundle(Path(directory))


FIXTURE_GIT = dict(
    os.environ,
    GIT_AUTHOR_NAME="Audit Fixture",
    GIT_AUTHOR_EMAIL="audit@example.invalid",
    GIT_COMMITTER_NAME="Audit Fixture",
    GIT_COMMITTER_EMAIL="audit@example.invalid",
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_NOSYSTEM="1",
)


def git_in(repo, *args, data=None, env=None):
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args],
            input=data,
            env=env or FIXTURE_GIT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def write_tree(repo, node):
    """Write nested {name: bytes or dict} into the object store; return the tree ID."""
    rows = []
    for name, value in sorted(node.items()):
        if isinstance(value, dict):
            rows.append(f"040000 tree {write_tree(repo, value)}\t{name}")
        else:
            digest = git_in(repo, "hash-object", "-w", "--stdin", data=value)
            rows.append(f"100644 blob {digest}\t{name}")
    return git_in(repo, "mktree", data=("\n".join(rows) + "\n").encode())


def crafted_commit(root, files):
    """A repository whose checked-out HEAD is a commit built straight from ``files``.

    ``git add`` refuses paths such as ``.git/index``; a commit made with plumbing
    holds them, and a fetched commit could too.
    """
    repo = root / "crafted"
    git_in(root, "init", "-q", str(repo))
    commit = git_in(repo, "commit-tree", "-m", "crafted", write_tree(repo, files))
    git_in(repo, "update-ref", "refs/heads/main", commit)
    git_in(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    return repo, commit


class StagingSafetyTests(unittest.TestCase):
    """Review round 1 findings R3-1 to R3-3: staging must stage exactly the commit."""

    def test_commit_cannot_run_a_host_command_while_staging(self):
        """R3-1: committed .git/commondir pointed Git at committed config (fsmonitor)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "MARKER"
            empty_index = root / "empty-index"
            git_in(root, "init", "-q", str(root / "scratch"))
            git_in(
                root / "scratch",
                "read-tree",
                "--empty",
                env=dict(FIXTURE_GIT, GIT_INDEX_FILE=str(empty_index)),
            )
            repo, commit = crafted_commit(
                root,
                {
                    ".git": {"commondir": b"../evil\n", "index": empty_index.read_bytes()},
                    "evil": {
                        "config": b"[core]\n\trepositoryformatversion = 0\n"
                        b"\tbare = false\n\tfsmonitor = sh evil/fsm.sh\n",
                        "fsm.sh": f'echo ran > "{marker.as_posix()}"\n'.encode(),
                        "objects": {"info": {"alternates": b"../../.git/objects\n"}},
                        "refs": {"keep": b""},
                    },
                    "README": b"ordinary\n",
                },
            )
            with self.assertRaisesRegex(ValueError, "Git metadata"):
                stage_source(repo, root / "staged", commit)
            self.assertFalse(marker.exists(), "the host ran a command from the commit")

    def test_paths_into_git_metadata_are_refused(self):
        for path in (".git/config", ".GIT/config", "sub/.Git/hooks/x", "GIT~1/config", "git~1"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "Git metadata"):
                    source_entries(listing(("100644", "blob", path)))
        rows = [("100644", "blob", path) for path in (".github/x", ".gitignore", "a.git/b")]
        self.assertEqual(len(source_entries(listing(*rows))), 3)

    def test_a_path_listed_twice_is_refused(self):
        """Fuzzing (Atheris) shrank this: a crafted tree object can list one path twice."""
        rows = [("100644", "blob", "A"), ("100644", "blob", "A")]
        with self.assertRaisesRegex(ValueError, "listed twice"):
            source_entries(listing(*rows))

    def test_names_windows_could_read_as_a_short_name_are_refused(self):
        """R3-3: on NTFS, AAAAAA~1 can name the folder AAAAAAAAAA."""
        for path in ("AAAAAA~1/b.py", "PROGRA~1", "dir/AB12~3.TXT", "x~1.py"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "not portable"):
                    source_entries(listing(("100644", "blob", path)))
        rows = [
            ("100644", "blob", path)
            for path in ("notes~", "a~b", "backup~1.toml", "LONGNAME9~1", "x~1y.toolong")
        ]
        self.assertEqual(len(source_entries(listing(*rows))), 5)

    def test_folders_that_alias_on_the_host_are_refused(self):
        """R3-3: a folder that already exists is never merged into another path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"Alpha/a.py": b"a\n", "beta/b.py": b"b\n"})
            staged = root / "staged"
            real_mkdir = Path.mkdir

            def mkdir(self, *args, **kwargs):  # emulate a host that also names Alpha "beta"
                real_mkdir(self, *args, **kwargs)
                if self == staged / "Alpha":
                    os.symlink("Alpha", staged / "beta", target_is_directory=True)

            try:
                os.symlink(root, root / "probe", target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")
            with patch.object(Path, "mkdir", mkdir):
                with self.assertRaisesRegex(ValueError, "alias"):
                    stage_source(source, staged, revision)

    def test_replace_refs_do_not_change_the_staged_tree(self):
        """R3-2: Git honours refs/replace/ unless told not to."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"README": b"committed\n"})
            (source / "README").write_bytes(b"replacement\n")
            git_in(source, "commit", "-qam", "other")
            other = git_in(source, "rev-parse", "HEAD")
            git_in(source, "reset", "-q", "--hard", revision)
            git_in(source, "replace", revision, other)
            records = stage_source(source, root / "staged", revision)
            self.assertEqual((root / "staged/README").read_bytes(), b"committed\n")
            self.assertEqual(records[0]["git_blob"], blob_digest(b"committed\n"))
            status = git_in(root / "staged", "status", "--porcelain", "--untracked-files=no")
            self.assertEqual(status, "")

    def test_inherited_git_variables_do_not_redirect_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"a.txt": b"a\n"})
            other = root / "other"
            git_in(root, "init", "-q", str(other))
            redirect = {
                "GIT_DIR": str(other / ".git"),
                "GIT_INDEX_FILE": str(root / "elsewhere-index"),
                "GIT_OBJECT_DIRECTORY": str(other / ".git/objects"),
            }
            with patch.dict(os.environ, redirect):
                records = stage_source(source, root / "staged", revision)
            self.assertEqual(records, [{"path": "a.txt", "git_blob": blob_digest(b"a\n")}])
            self.assertFalse((root / "elsewhere-index").exists())
            self.assertTrue((root / "staged/.git/index").is_file())

    def test_windows_host_skips_probes_that_mean_nothing_in_the_container(self):
        """R3-4: a Windows path or PID names nothing inside the Linux container."""
        sentinel = Path("out") / "host-only-sentinel"
        self.assertEqual(
            isolated_runner.boundary_arguments(sentinel, 4242, windows=False),
            ["--sentinel", str(sentinel), "--host-pid", "4242"],
        )
        self.assertEqual(isolated_runner.boundary_arguments(sentinel, 4242, windows=True), [])
        command = execution_command("sha256:" + "0" * 64, ".", ".", ".", None, None, 65534, 65534)
        self.assertNotIn("--sentinel", command)
        self.assertNotIn("--host-pid", command)


def git_output(*items):
    """Fake ``git cat-file --batch`` output from (digest, payload) pairs."""
    return b"".join(f"{d} blob {len(p)}\n".encode() + p + b"\n" for d, p in items)


class RunnerBranchTests(unittest.TestCase):
    """Error paths that the end-to-end tests do not reach (coverage, profile rule 20)."""

    def test_failed_command_names_the_program_and_its_error(self):
        script = "import sys; sys.stderr.write('broken'); raise SystemExit(3)"
        with self.assertRaisesRegex(RuntimeError, "exited 3: broken"):
            checked([sys.executable, "-c", script])

    def test_non_positive_execution_limits_are_refused(self):
        for limits in ({"timeout": 0}, {"max_log_bytes": 0}):
            with self.subTest(limits=limits):
                with self.assertRaisesRegex(ValueError, "positive"):
                    run_bounded([sys.executable, "-c", "pass"], **limits)

    def test_log_reader_failure_is_an_error_not_a_quiet_empty_log(self):
        real = subprocess.Popen

        class Broken:
            def read1(self, size):
                raise OSError("pipe broke")

            def close(self):
                pass

        def popen(*args, **kwargs):
            process = real(*args, **kwargs)
            process.stdout.close()
            process.stdout = Broken()
            return process

        with patch("isolated_runner.subprocess.Popen", side_effect=popen):
            with self.assertRaisesRegex(RuntimeError, "log reader failed"):
                run_bounded([sys.executable, "-c", "pass"], timeout=30)

    def test_reader_that_cannot_start_still_ends_the_child(self):
        started = []
        real = subprocess.Popen

        def popen(*args, **kwargs):
            started.append(real(*args, **kwargs))
            return started[-1]

        with (
            patch("isolated_runner.subprocess.Popen", side_effect=popen),
            patch("isolated_runner.threading.Thread.start", side_effect=RuntimeError("no thread")),
        ):
            with self.assertRaisesRegex(RuntimeError, "no thread"):
                run_bounded([sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertIsNotNone(started[0].poll())
        self.assertTrue(started[0].stdout.closed)

    def test_git_object_output_is_checked(self):
        good = b"payload\n"
        digest = blob_digest(good)
        cases = {
            "exited 1": subprocess.CompletedProcess([], 1, b"", b""),
            "ended early": subprocess.CompletedProcess([], 0, git_output((digest, good))[:-3], b""),
            "does not match": subprocess.CompletedProcess(
                [], 0, git_output((digest, b"payload!")).replace(b" 9\n", b" 8\n"), b""
            ),
            "Unexpected": subprocess.CompletedProcess(
                [], 0, git_output((digest, good)) + b"x", b""
            ),
            "missing or not a blob(?# wrong object ID)": subprocess.CompletedProcess(
                [], 0, git_output(("1" * 40, good)), b""
            ),
            "missing or not a blob(?# size not a number)": subprocess.CompletedProcess(
                [], 0, git_output((digest, good)).replace(b" 8\n", b" eight\n", 1), b""
            ),
            "ended early(?# no newline after the payload)": subprocess.CompletedProcess(
                [], 0, git_output((digest, good))[:-1] + b"!", b""
            ),
        }
        for message, result in cases.items():
            with self.subTest(message=message):
                with patch("isolated_runner.subprocess.run", return_value=result):
                    with self.assertRaisesRegex((RuntimeError, ValueError), message):
                        read_blobs(Path("."), [digest])

    def test_revision_must_be_full_and_checked_out(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"a.txt": b"a\n"})
            with self.assertRaisesRegex(ValueError, "full Git SHA"):
                stage_source(source, root / "one", revision[:12])
            with self.assertRaisesRegex(ValueError, "differs from the expected"):
                stage_source(source, root / "two", "0" * 40)

    def test_borrowed_object_store_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"a.txt": b"a\n"})
            (source / ".git/objects/info").mkdir(exist_ok=True)
            (source / ".git/objects/info/alternates").write_text("/elsewhere\n")
            with self.assertRaisesRegex(ValueError, "Materialize Git objects"):
                stage_source(source, root / "staged", revision)

    def test_linked_object_store_entry_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"a.txt": b"a\n"})
            try:
                (source / ".git/objects/zz").symlink_to(root, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")
            with self.assertRaisesRegex(ValueError, "Symlink in Git object store"):
                stage_source(source, root / "staged", revision)

    def test_shallow_clone_keeps_its_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin, _ = fixture_repository(root, {"a.txt": b"a\n"})
            (origin / "b.txt").write_bytes(b"b\n")
            subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(origin),
                    "-c",
                    "user.name=F",
                    "-c",
                    "user.email=f@x.invalid",
                    "commit",
                    "-qm",
                    "second",
                ],
                check=True,
            )
            clone = root / "clone"
            subprocess.run(
                ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(clone)], check=True
            )
            revision = subprocess.check_output(
                ["git", "-C", str(clone), "rev-parse", "HEAD"], text=True
            ).strip()
            records = stage_source(clone, root / "staged", revision)
            self.assertEqual([row["path"] for row in records], ["a.txt", "b.txt"])
            self.assertEqual(
                (root / "staged/.git/shallow").read_bytes(), (clone / ".git/shallow").read_bytes()
            )
            # Git accepts upper-case hex here; the runner accepts only its own spelling.
            shallow = (clone / ".git/shallow").read_text()
            (clone / ".git/shallow").write_text(shallow.upper())
            with self.assertRaisesRegex(ValueError, "shallow-boundary"):
                stage_source(clone, root / "again", revision)


class SemanticCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "metrics.json").write_text('{"return":0.25}', encoding="utf-8")
        (self.root / "figure.png").write_bytes(b"TOY_NONEMPTY_FIGURE")

    def compressed(self, value=b"value\n1\n", mtime=0):
        path = self.root / "table.csv.gz"
        path.write_bytes(gzip.compress(value, mtime=mtime))
        return path

    def test_compressed_numeric_change_is_detected(self):
        self.compressed()
        before = semantic_hash(self.root)
        self.compressed(b"value\n2\n")
        self.assertNotEqual(before, semantic_hash(self.root))

    def test_gzip_header_timestamp_is_not_table_content(self):
        self.compressed(mtime=1)
        before = semantic_hash(self.root)
        self.compressed(mtime=2)
        self.assertEqual(before, semantic_hash(self.root))

    def test_deleted_compressed_table_is_detected(self):
        path = self.compressed()
        before = semantic_hash(self.root)
        path.unlink()
        self.assertNotEqual(before, semantic_hash(self.root))

    def test_added_compressed_table_is_detected(self):
        before = semantic_hash(self.root)
        self.compressed()
        self.assertNotEqual(before, semantic_hash(self.root))

    def test_corrupt_compressed_table_is_rejected(self):
        for payload in (b"not a gzip stream", gzip.compress(b"value\n1\n", mtime=0)[:-2]):
            with self.subTest(payload=payload):
                (self.root / "table.csv.gz").write_bytes(payload)
                with self.assertRaisesRegex(ValueError, "Invalid compressed CSV"):
                    semantic_hash(self.root)

    def ledger(self, **changes):
        record = {"recorded_at": "first", "factor_id": "A", "n_trials": 20, **changes}
        (self.root / "ledger.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    def test_ledger_numeric_change_is_detected(self):
        self.ledger()
        before = semantic_hash(self.root)
        self.ledger(n_trials=21)
        self.assertNotEqual(before, semantic_hash(self.root))

    def test_ledger_identity_change_is_detected(self):
        self.ledger()
        before = semantic_hash(self.root)
        self.ledger(factor_id="B")
        self.assertNotEqual(before, semantic_hash(self.root))

    def test_declared_ledger_timestamp_change_is_ignored(self):
        self.ledger()
        before = semantic_hash(self.root)
        self.ledger(recorded_at="later")
        self.assertEqual(before, semantic_hash(self.root))

    def test_other_artifact_changes_are_not_silently_ignored(self):
        path = self.root / "artifact.bin"
        path.write_bytes(b"first")
        before = semantic_hash(self.root)
        path.write_bytes(b"changed")
        self.assertNotEqual(before, semantic_hash(self.root))

    def test_manifest_records_every_file_and_its_comparison(self):
        self.compressed()
        self.ledger()
        (self.root / "artifact.bin").write_bytes(b"first")
        manifest = semantic_manifest(self.root)
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(
            {row["path"] for row in manifest["records"]},
            {"metrics.json", "table.csv.gz", "ledger.jsonl", "artifact.bin"},
        )
        self.assertEqual(manifest["figures_present_nonempty"], ["figure.png"])
        self.assertTrue(all(row["comparison"] and row["sha256"] for row in manifest["records"]))


class InstalledGraphTests(unittest.TestCase):
    def test_continuation_and_hashes_are_parsed(self):
        text = "demo==1.2 \\\n    --hash=sha256:abcdef \\\n    --hash=sha256:fedcba\n"
        parsed = applicable_requirements(text)
        self.assertEqual([str(item) for item in parsed], ["demo==1.2"])

    def test_python_specific_versions_are_selected(self):
        text = "numpy==2.4.6 ; python_version < '3.12'\nnumpy==2.5.3 ; python_version >= '3.12'\n"
        old = applicable_requirements(text, {"python_version": "3.11"})
        new = applicable_requirements(text, {"python_version": "3.13"})
        self.assertEqual(str(old[0].specifier), "==2.4.6")
        self.assertEqual(str(new[0].specifier), "==2.5.3")

    def test_actual_version_drift_is_rejected(self):
        parsed = applicable_requirements("demo==1.2\n")
        with self.assertRaisesRegex(ValueError, "installed 1.3"):
            verify_versions(parsed, lambda name: "1.3")

    def test_matching_version_is_recorded(self):
        parsed = applicable_requirements("demo==1.2\n")
        self.assertEqual(
            verify_versions(parsed, lambda name: "1.2"), [{"name": "demo", "version": "1.2"}]
        )


if __name__ == "__main__":
    unittest.main()
