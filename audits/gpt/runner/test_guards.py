import copy
import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CONTRACT_CHECKS", "1")

import isolated_runner
import runner_workload
import verify_snapshot
from ci_evidence import classify
from isolated_runner import (
    blob_digest,
    ca_bundle,
    checked,
    container_user,
    docker_command,
    execution_command,
    git_environment,
    host_tool,
    program,
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

    def test_manifest_of_the_wrong_shape_is_rejected(self):
        """Review round 6 (A3): a list where an object belongs crashed with AttributeError,
        which the command line did not catch."""
        request = self.expected["request"]
        for manifest in ([], {"request": request, "files": []}):
            with self.subTest(manifest=manifest):
                self.reference.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(SnapshotError, "files object"):
                    verify(self.reference, self.snapshot)

    def test_command_line_rejects_malformed_input_without_a_traceback(self):
        """CONTRACT.md W3: wrong input is rejected with exit 2, never a traceback."""
        script = Path(__file__).with_name("verify_snapshot.py")
        manifest = self.snapshot / "snapshot.json"
        request = self.expected["request"]
        cases = {
            "nested snapshot manifest": (None, "[" * 100000),
            "entry is a list": ({"request": request, "files": {"AAA": []}}, None),
            "request is text": ({"request": "2010", "files": {}}, None),
            "manifest not UTF-8": ("\udcff", None),
        }
        for case, (reference, snapshot_text) in cases.items():
            with self.subTest(case=case):
                self.save()
                if reference == "\udcff":
                    self.reference.write_bytes(b'{"files": {"\xff": 1}}')
                elif reference is not None:
                    self.reference.write_text(json.dumps(reference))
                if snapshot_text is not None:
                    manifest.write_text(snapshot_text)
                run = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--expected",
                        str(self.reference),
                        "--snapshot",
                        str(self.snapshot),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertNotIn("Traceback", run.stderr)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(json.loads(run.stdout)["status"], "rejected")

    def test_present_input_of_the_wrong_kind_is_rejected_not_blocked(self):
        """Review round 6 (A4): only missing input is blocked; a folder or a special
        file where a regular file belongs is rejected."""
        self.file.unlink()
        self.file.mkdir()
        with self.assertRaisesRegex(SnapshotError, "not a regular file"):
            verify(self.reference, self.snapshot)
        self.file.rmdir()
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.file)
            with self.assertRaisesRegex(SnapshotError, "not a regular file"):
                verify(self.reference, self.snapshot)
            self.file.unlink()
        self.file.write_bytes(self.payload)
        manifest = self.snapshot / "snapshot.json"
        manifest.unlink()
        manifest.mkdir()
        with self.assertRaisesRegex(SnapshotError, "manifest is not a regular file"):
            verify(self.reference, self.snapshot)
        not_a_folder = self.root / "snapshot-file"
        not_a_folder.write_bytes(b"")
        with self.assertRaisesRegex(SnapshotError, "root is not a directory"):
            verify(self.reference, not_a_folder)

    def test_malformed_or_unsafe_manifest_is_rejected_even_without_a_snapshot(self):
        """Review round 7 (F1, W3): a malformed entry or an unsafe path was reported as
        blocked when the raw file or the whole snapshot was missing."""
        request = self.expected["request"]
        entry = {"path": "raw/a", "bytes": 1, "sha256": "0" * 64}
        cases = {
            "no hash": {"AAA": {"path": "raw/AAA.json"}},
            "bytes as text": {"AAA": dict(entry, bytes="1")},
            "bytes as bool": {"AAA": dict(entry, bytes=True)},
            "entry is a number": {"AAA": 5},
            "parent escape": {"AAA": dict(entry, path="../a")},
            "duplicate": {"AAA": entry, "BBB": dict(entry, path="raw/./a")},
        }
        for case, files in cases.items():
            for snapshot in (self.snapshot, self.root / "missing"):
                with self.subTest(case=case, snapshot=snapshot.name):
                    self.expected = {"request": request, "files": files}
                    self.save()
                    self.file.unlink(missing_ok=True)
                    with self.assertRaises(SnapshotError):
                        verify(self.reference, snapshot)

    def test_entry_that_could_never_verify_is_rejected_even_without_a_snapshot(self):
        """Review round 8 (W3): a digest that is not 64 lower-case hex digits, a negative
        size, the raw folder itself or a NUL in the path passed the type check, so such
        a manifest was reported as blocked while its snapshot or raw file was missing."""
        request = self.expected["request"]
        entry = {"path": "raw/a", "bytes": 1, "sha256": "0" * 64}
        cases = {
            "short digest": dict(entry, sha256="abc"),
            "upper-case digest": dict(entry, sha256="A" * 64),
            "negative size": dict(entry, bytes=-1),
            "raw folder itself": dict(entry, path="raw"),
            "NUL in path": dict(entry, path="raw/a\0b"),
        }
        for case, value in cases.items():
            for snapshot in (self.snapshot, self.root / "missing"):
                with self.subTest(case=case, snapshot=snapshot.name):
                    self.expected = {"request": request, "files": {"AAA": value}}
                    self.save()
                    with self.assertRaises(SnapshotError):
                        verify(self.reference, snapshot)

    def test_raw_paths_that_no_file_can_have_are_rejected(self):
        """Review round 9 (W3): a raw path that is also another entry's folder can never
        verify, and a name over 255 bytes or with a lone surrogate is refused on every
        host, yet each was reported as blocked: without a snapshot, and for the folder
        clash even with every file that can exist in place."""
        request = self.expected["request"]
        good = self.expected["files"]["AAA"]
        entry = {"bytes": 1, "sha256": "0" * 64}
        cases = {
            "file and folder": {"AAA": good, "BBB": dict(entry, path="raw/AAA.json/x")},
            "name over 255 bytes": {"AAA": dict(entry, path="raw/" + "a" * 256)},
            "lone surrogate": {"AAA": dict(entry, path="raw/\ud800")},
        }
        for case, files in cases.items():
            for snapshot in (self.snapshot, self.root / "missing"):
                with self.subTest(case=case, snapshot=snapshot.name):
                    self.expected = {"request": request, "files": files}
                    self.save()
                    with self.assertRaises(SnapshotError) as caught:
                        verify(self.reference, snapshot)
                    if case == "file and folder":
                        self.assertEqual(
                            str(caught.exception), "Raw path is a folder of another raw path"
                        )
        # A 255-byte name is still a name (checked without the file system, since a
        # Windows host may not open a path over 260 characters).
        self.assertTrue(verify_snapshot._name_fits("a" * 255))

    def test_raw_path_no_path_call_can_open_is_rejected(self):
        """Review round 10 (W3): a raw path of 4096 UTF-8 bytes or more (Linux PATH_MAX)
        can never be opened wherever the snapshot is, yet was reported as blocked when
        the snapshot was missing."""
        request = self.expected["request"]
        entry = {"bytes": 1, "sha256": "0" * 64}
        long_path = "raw/" + "/".join(["d" * 200] * 21) + "/f.json"
        self.assertGreaterEqual(len(long_path.encode()), 4096)
        for snapshot in (self.snapshot, self.root / "missing"):
            with self.subTest(snapshot=snapshot.name):
                self.expected = {"request": request, "files": {"AAA": dict(entry, path=long_path)}}
                self.save()
                with self.assertRaisesRegex(SnapshotError, "^Unsafe raw path for AAA$"):
                    verify(self.reference, snapshot)
        # One byte shorter is still a path (checked without the file system).
        fits = "raw/" + "/".join(["d" * 255] * 15) + "/" + "e" * 251
        self.assertEqual(len(fits.encode()), 4095)
        verify_snapshot._entry("AAA", dict(entry, path=fits))

    def test_an_empty_raw_file_verifies(self):
        """Mutation testing (round 9): no test had a raw file of 0 bytes, so a check that
        refused a size of 0 (not only a negative one) went unnoticed."""
        self.file.write_bytes(b"")
        self.expected["files"]["AAA"].update(bytes=0, sha256=hashlib.sha256(b"").hexdigest())
        self.save()
        result = verify(self.reference, self.snapshot)
        self.assertEqual((result["status"], result["verified_bytes"]), ("verified", 0))

    def test_raw_paths_windows_reads_as_rooted_or_drive_paths_are_rejected(self):
        """Review round 6 (C1): on Windows these made the symlink walk loop forever."""
        for raw in ("raw/\\x", "raw/C:x", "raw/sub\\..\\x", "raw/name:stream"):
            with self.subTest(raw=raw):
                self.expected["files"]["AAA"]["path"] = raw
                self.save()
                with self.assertRaisesRegex(SnapshotError, "Unsafe raw path"):
                    verify(self.reference, self.snapshot)

    def test_raw_names_no_windows_file_can_have_are_rejected(self):
        """Review round 10 (C1, W3): no Windows file name holds ? * " < > | or a control
        character. Windows' stat fails with error 123, which pathlib and os.path read as
        "absent", so such an entry was reported as blocked with every file in place (shown
        on the windows-2025 job). They are refused on every host, as output names are."""
        request = self.expected["request"]
        good = self.expected["files"]["AAA"]
        for name in ("a?b", "a*b", 'a"b', "a<b", "a>b", "a|b", "a\x01b", "a\x1fb", "a\x7fb"):
            with self.subTest(name=repr(name)):
                entry = {"bytes": 1, "sha256": "0" * 64, "path": f"raw/{name}.json"}
                self.expected = {"request": request, "files": {"AAA": good, "BBB": entry}}
                self.save()
                try:
                    result = verify(self.reference, self.snapshot)
                except SnapshotError as exc:
                    self.assertEqual(str(exc), "Unsafe raw path for BBB")
                else:
                    self.fail(f"{result['status']} for a name no Windows file can have")

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

    def save_utf8(self):
        """Both manifests as UTF-8 text with non-ASCII characters left unescaped."""
        text = json.dumps(self.expected, ensure_ascii=False)
        for path in (self.reference, self.snapshot / "snapshot.json"):
            path.write_text(text, encoding="utf-8")

    def test_each_result_is_reported_in_full(self):
        """Mutation testing (round 8): most tests read only a result's status, and no
        manifest held a non-ASCII path (read with the locale's encoding on Windows)."""
        second = "café".encode()
        (self.snapshot / "raw" / "BÉ.json").write_bytes(second)
        self.expected["files"]["BÉ"] = {
            "path": "raw/BÉ.json",
            "bytes": len(second),
            "sha256": hashlib.sha256(second).hexdigest(),
        }
        self.save_utf8()
        common = {"request": self.expected["request"], "observations_interpreted": False}
        self.assertEqual(
            verify(self.reference, self.snapshot),
            {
                "status": "verified",
                "files": 2,
                "verified_bytes": len(self.payload) + len(second),
                "missing": [],
                **common,
            },
        )
        self.file.unlink()
        self.assertEqual(
            verify(self.reference, self.snapshot),
            {
                "status": "blocked",
                "files": 2,
                "verified_bytes": len(second),
                "missing": ["raw/AAA.json"],
                **common,
            },
        )
        (self.snapshot / "snapshot.json").unlink()
        self.assertEqual(
            verify(self.reference, self.snapshot),
            {"status": "blocked", "reason": "snapshot manifest unavailable"},
        )
        self.assertEqual(
            verify(self.reference, self.root / "missing"),
            {"status": "blocked", "reason": "matching snapshot directory unavailable"},
        )

    def test_a_missing_file_does_not_end_the_check_of_later_files(self):
        self.expected["files"]["BBB"] = {
            "path": "raw/BBB.json",
            "bytes": len(self.payload),
            "sha256": "0" * 64,
        }
        (self.snapshot / "raw" / "BBB.json").write_bytes(self.payload)
        self.save()
        self.file.unlink()
        with self.assertRaisesRegex(SnapshotError, "^Wrong SHA-256 for BBB$"):
            verify(self.reference, self.snapshot)

    def test_a_one_day_request_is_permitted(self):
        self.expected["request"] = {"start": "2024-12-31", "end": "2024-12-31"}
        self.save()
        self.assertEqual(verify(self.reference, self.snapshot)["status"], "verified")

    def test_each_rejection_names_its_reason(self):
        """Mutation testing (round 8): the command line prints the reason, and most tests
        matched only a word of it."""
        base = copy.deepcopy(self.expected)

        def manifest(change):
            def apply(reference, snapshot):
                expected = copy.deepcopy(base)
                change(expected)
                for path in (reference, snapshot / "snapshot.json"):
                    path.write_text(json.dumps(expected), encoding="utf-8")
                return snapshot

            return apply

        def snapshot_manifest(text):
            def apply(reference, snapshot):
                (snapshot / "snapshot.json").write_text(text, encoding="utf-8")
                return snapshot

            return apply

        def raw(replace):
            def apply(reference, snapshot):
                replace(snapshot / "raw" / "AAA.json", snapshot)
                return snapshot

            return apply

        def linked_root(reference, snapshot):
            link = snapshot.with_name("link")
            link.symlink_to(snapshot, target_is_directory=True)
            return link

        def file_root(reference, snapshot):
            other = snapshot.with_name("file")
            other.write_bytes(b"")
            return other

        def linked_manifest(reference, snapshot):
            moved = snapshot.with_name("moved.json")
            (snapshot / "snapshot.json").rename(moved)
            (snapshot / "snapshot.json").symlink_to(moved)
            return snapshot

        def folder_manifest(reference, snapshot):
            (snapshot / "snapshot.json").unlink()
            (snapshot / "snapshot.json").mkdir()
            return snapshot

        def linked_raw(path, snapshot):
            moved = snapshot.with_name("outside.json")
            path.rename(moved)
            path.symlink_to(moved)

        def folder_raw(path, snapshot):
            path.unlink()
            path.mkdir()

        entry = base["files"]["AAA"]
        cases = {
            "Manifest must be an object with a files object": manifest(
                lambda m: m.update(files=[])
            ),
            "Manifest lists no raw files": manifest(lambda m: m.update(files={})),
            "Manifest request must name its start and end dates": manifest(
                lambda m: m.pop("request")
            ),
            "Only an already-inspected pre-2025 request is permitted": manifest(
                lambda m: m["request"].update(start="2024-02-01", end="2024-01-31")
            ),
            "Malformed manifest entry for AAA": manifest(lambda m: m["files"]["AAA"].pop("sha256")),
            "Unsafe raw path for AAA": manifest(
                lambda m: m["files"]["AAA"].update(path="other/AAA.json")
            ),
            "Duplicate raw path": manifest(lambda m: m["files"].update(BBB=dict(entry))),
            "Snapshot root must not be a symlink": linked_root,
            "Snapshot root is not a directory": file_root,
            "Snapshot manifest must not be a symlink": linked_manifest,
            "Snapshot manifest is not a regular file": folder_manifest,
            "Snapshot manifest differs from the recorded request/file identity": (
                snapshot_manifest(json.dumps({**base, "request": {"start": "2011-01-01"}}))
            ),
            "JSON nested too deeply: snapshot.json": snapshot_manifest("[" * 100000),
            "Symlink in raw path for AAA": raw(linked_raw),
            "Raw path is not a regular file for AAA": raw(folder_raw),
            "Wrong byte count for AAA": raw(lambda path, _: path.write_bytes(b"x")),
            "Wrong SHA-256 for AAA": raw(
                lambda path, _: path.write_bytes(self.payload.replace(b"t", b"T"))
            ),
        }
        for number, (reason, apply) in enumerate(cases.items()):
            with self.subTest(reason=reason):
                root = self.root / f"case{number}"
                snapshot = root / "snapshot"
                (snapshot / "raw").mkdir(parents=True)
                (snapshot / "raw" / "AAA.json").write_bytes(self.payload)
                reference = root / "expected.json"
                for path in (reference, snapshot / "snapshot.json"):
                    path.write_text(json.dumps(base), encoding="utf-8")
                target = apply(reference, snapshot)
                with self.assertRaises(SnapshotError) as caught:
                    verify(reference, target)
                self.assertEqual(str(caught.exception), reason)


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


REAL_HOST_TOOL = isolated_runner.host_tool


def docker_anywhere(name):
    """Tests that only build a Docker command must also run where Docker is not
    installed, such as inside the audit container (CI on b27cf37)."""
    return "/abs/docker" if name == "docker" else REAL_HOST_TOOL(name)


class RunnerContractTests(unittest.TestCase):
    def setUp(self):
        stub = patch("isolated_runner.host_tool", side_effect=docker_anywhere)
        stub.start()
        self.addCleanup(stub.stop)

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
            # Review round 8: the workload must be PID 1 for its cleanup (W2), whatever
            # the daemon's default for an init process.
            "--init=false",
        ):
            self.assertIn(required, command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("--env-file", command)
        # Review round 9: the Docker CLI fills in every proxy variable that config.json
        # names (httpProxy, httpsProxy, ftpProxy, noProxy, allProxy) and the run leaves unset.
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "NO_PROXY", "ALL_PROXY"):
            for variant in (name, name.lower()):
                self.assertIn(variant + "=", command)
        self.assertFalse(any("AUDIT_HOST_CANARY=" in item for item in command))
        self.assertTrue(any("dst=/input,readonly" in item for item in command))
        self.assertTrue(any("dst=/audit,readonly" in item for item in command))
        self.assertFalse(any("docker.sock,dst=" in item for item in command))

    def test_the_container_command_is_exactly_the_documented_one(self):
        """Mutation testing (round 9): the test above checks flags one by one, so a
        changed environment value, mount target, tmpfs option, workload path or probe
        argument, or an off-by-one UID check, went unnoticed (only the CI audit would
        have failed)."""
        paths = {name: Path(f"/tmp/{name}").resolve() for name in ("source", "tools", "output")}
        command = execution_command(
            "sha256:" + "0" * 64,
            paths["source"],
            paths["output"],
            paths["tools"],
            "/tmp/sentinel",
            12345,
            1,
            1,
        )
        environment = {
            "HOME": "/work/home",
            "MPLCONFIGDIR": "/work/matplotlib",
            "TMPDIR": "/work/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
        }
        proxies = ("HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY", "NO_PROXY")
        environment.update({name: "" for name in proxies})
        environment.update({name.lower(): "" for name in proxies})
        expected = [
            "run",
            "--rm",
            "--init=false",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=256",
            "--memory=2g",
            "--cpus=2",
            "--user",
            "1:1",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m",
            "--mount",
            f"type=bind,src={paths['source']},dst=/input,readonly",
            "--mount",
            f"type=bind,src={paths['tools']},dst=/audit,readonly",
            "--mount",
            f"type=bind,src={paths['output']},dst=/work",
        ]
        for name, value in environment.items():
            expected += ["--env", f"{name}={value}"]
        expected += ["sha256:" + "0" * 64, "python", "/audit/runner_workload.py"]
        if os.name != "nt":
            expected += ["--sentinel", "/tmp/sentinel", "--host-pid", "12345"]
        self.assertTrue(command[1].startswith("--host="), command[:2])
        self.assertEqual(command[2:], expected)
        messages = {
            "Container execution requires an unprivileged UID": ("sha256:" + "0" * 64, 0, 1),
            "Execution requires a recorded immutable image ID": ("python:3.13", 1, 1),
        }
        for message, (image, uid, gid) in messages.items():
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as caught:
                    execution_command(image, "/tmp/a", "/tmp/b", "/tmp/c", None, None, uid, gid)
                self.assertEqual(str(caught.exception), message)
        with self.assertRaises(ValueError) as caught:
            execution_command(
                "sha256:" + "0" * 64, "/tmp/a,b", "/tmp/b", "/tmp/c", None, None, 1, 1
            )
        self.assertEqual(str(caught.exception), "A mount path must not contain a comma")

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

    def test_files_sharing_folders_are_staged(self):
        files = {"dir/a.txt": b"a\n", "dir/b.txt": b"b\n", "dir/sub/c.txt": b"c\n", "top": b"t"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, files)
            records = stage_source(source, root / "staged", revision)
            self.assertEqual([row["path"] for row in records], sorted(files))
            for name, payload in files.items():
                self.assertEqual((root / "staged" / name).read_bytes(), payload)

    def test_host_tools_come_only_from_absolute_path_folders(self):
        """Review round 5: never a program from the current folder or a relative entry."""
        filename = "tool.cmd" if os.name == "nt" else "tool"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in (root / "cwd", root / "cwd/relative", root / "bin"):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / filename).write_text("", encoding="utf-8")
                (folder / filename).chmod(0o755)
            listed = os.pathsep.join([".", "", "relative", str(root / "bin")])
            previous = os.getcwd()
            os.chdir(root / "cwd")
            try:
                with patch.dict(os.environ, {"PATH": listed}):
                    self.assertEqual(host_tool("tool"), str(root / "bin" / filename))
                    self.assertEqual(program("tool"), str(root / "bin" / filename))
                with patch.dict(os.environ, {"PATH": os.pathsep.join([".", "relative"])}):
                    self.assertIsNone(host_tool("tool"))
                    with self.assertRaisesRegex(RuntimeError, "tool executable unavailable"):
                        program("tool")
            finally:
                os.chdir(previous)

    def test_a_folder_named_like_a_program_is_skipped(self):
        """Mutation testing: a folder carries the search bit, so it must also be a file."""
        filename = "tool.cmd" if os.name == "nt" else "tool"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first" / filename).mkdir(parents=True)
            (root / "second").mkdir()
            (root / "second" / filename).write_text("", encoding="utf-8")
            (root / "second" / filename).chmod(0o755)
            listed = os.pathsep.join([str(root / "first"), str(root / "second")])
            with patch.dict(os.environ, {"PATH": listed}):
                self.assertEqual(host_tool("tool"), str(root / "second" / filename))

    def test_no_path_variable_finds_no_program(self):
        with patch.dict(os.environ):
            os.environ.pop("PATH", None)
            self.assertIsNone(host_tool("git"))

    @unittest.skipIf(os.name == "nt", "simulates the Windows lookup with POSIX file names")
    def test_windows_lookup_adds_pathext_suffixes_only_to_a_bare_name(self):
        """Mutation testing: the Windows branch ran only on Windows CI, never under mutmut."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for filename in ("tool.xyz", "tool.bat", "solo.com", "Named.Cmd"):
                (folder / filename).write_text("", encoding="utf-8")
                (folder / filename).chmod(0o755)
            with patch.object(isolated_runner.os, "name", "nt"):
                # A POSIX folder has no drive, so the drive-less PATH guard skips it.
                with patch.dict(os.environ, {"PATH": directory, "PATHEXT": ".XYZ;.BAT;.CMD"}):
                    self.assertIsNone(host_tool("tool"))
                # Give every folder a drive so the PATHEXT handling itself is tested.
                with patch.object(isolated_runner.os.path, "splitdrive", lambda path: ("C:", path)):
                    with patch.dict(os.environ, {"PATH": directory, "PATHEXT": ".XYZ;.BAT;.CMD"}):
                        self.assertEqual(host_tool("tool"), str(folder / "tool.xyz"))
                        self.assertEqual(host_tool("Named.Cmd"), str(folder / "Named.Cmd"))
                        self.assertIsNone(host_tool("solo"))
                    with patch.dict(os.environ, {"PATH": directory}):
                        os.environ.pop("PATHEXT", None)
                        self.assertEqual(host_tool("solo"), str(folder / "solo.com"))
                        self.assertEqual(host_tool("tool"), str(folder / "tool.bat"))

    def test_collection_checks_refuse_a_host_that_is_not_linux(self):
        """Review round 6: the container probes take a host path and process ID, which
        name nothing inside the Linux container from a Windows or macOS host."""
        import collection_checks

        argv = ["collection_checks.py", "--python-version", "3.11", "--output", "unused"]
        created = AssertionError("collection_checks went on to create its output")
        with patch.object(sys, "argv", argv), patch.object(sys, "platform", "win32"):
            with patch.object(Path, "mkdir", side_effect=created):
                with self.assertRaisesRegex(SystemExit, "Linux host"):
                    collection_checks.main()

    def test_checked_returns_at_its_timeout_when_a_grandchild_holds_the_pipe(self):
        """Review round 6 (C4): on Windows, subprocess.run reads the pipes to their end
        after the kill, so a launcher's child (Git for Windows' cmd\\git.exe, a Docker
        CLI plugin) kept checked() waiting until that child exited."""
        script = (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(15)'], "
            "stdout=sys.stdout, stderr=sys.stderr); time.sleep(60)"
        )
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            isolated_runner.checked([sys.executable, "-c", script], timeout=2)
        self.assertLess(time.monotonic() - started, 10)

    def test_every_host_program_runs_through_the_bounded_helper(self):
        """Review round 6 (C4): the image build (a Docker CLI plugin), the Git object
        reads, the tree listing and the container removal called subprocess.run
        directly, so on Windows their timeouts could wait for a grandchild too."""
        import ast

        tree = ast.parse(Path(isolated_runner.__file__).read_text(encoding="utf-8"))
        direct = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        self.assertEqual(direct, [], "lines that call subprocess.run directly")

    def test_bounded_helper_ends_its_program_when_the_wait_is_interrupted(self):
        """Review round 7: subprocess.run killed its program on any exception, such as
        KeyboardInterrupt; run_captured killed it only at its timeout."""
        made = []

        class Interrupted(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                made.append(self)

            def communicate(self, *args, **kwargs):
                raise KeyboardInterrupt

        with patch.object(isolated_runner.subprocess, "Popen", Interrupted):
            with self.assertRaises(KeyboardInterrupt):
                isolated_runner.run_captured(
                    [sys.executable, "-c", "import time; time.sleep(60)"], timeout=60
                )
        try:
            self.assertIsNotNone(made[0].returncode, "the program still runs")
        finally:
            if made[0].poll() is None:
                made[0].kill()
                made[0].wait()

    def test_bounded_helper_returns_at_its_timeout_while_input_is_unread(self):
        """Review round 7: Python 3.11 on Windows writes the input before it starts
        timing, so a program that stopped reading its input (git cat-file with a
        request larger than the pipe) kept run_captured waiting past its timeout."""
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            isolated_runner.run_captured(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                input=b"x" * (1 << 20),
                timeout=2,
            )
        self.assertLess(time.monotonic() - started, 10)

    def test_bounded_helper_passes_input_and_keeps_bytes(self):
        echo = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()[::-1])"
        result = isolated_runner.run_captured(
            [sys.executable, "-c", echo], input=b"ab\x00", timeout=60
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"\x00ba", b""))

    @unittest.skipUnless(os.name == "nt", "a Windows path without a drive")
    def test_ca_bundle_ignores_a_file_at_the_current_drive_root(self):
        """Review round 6 (C2): "/etc/ssl/certs/..." names a folder on the current drive
        on Windows, where any local user may create it."""
        planted = Path(os.path.abspath("/etc/ssl/certs/ca-certificates.crt"))
        created = not planted.exists()
        if created:
            planted.parent.mkdir(parents=True, exist_ok=True)
            planted.write_text(
                "-----BEGIN CERTIFICATE-----\nplanted\n-----END CERTIFICATE-----\n",
                encoding="ascii",
            )
        try:
            with tempfile.TemporaryDirectory() as directory:
                try:
                    chosen = ca_bundle(Path(directory))
                except RuntimeError:
                    chosen = None
                self.assertNotEqual(chosen and Path(chosen).resolve(), planted.resolve())
        finally:
            if created:
                planted.unlink()

    @unittest.skipUnless(os.name == "nt", "a Windows path without a drive")
    def test_host_tools_never_come_from_a_path_entry_without_a_drive(self):
        """Review round 6 (C3): Python 3.11 calls "\\tools" absolute, yet it names a
        folder at the current drive's root."""
        folder = Path(os.path.abspath("\\audit-test-tools-" + uuid.uuid4().hex))
        folder.mkdir()
        try:
            (folder / "docker.exe").write_bytes(b"")
            with patch.dict(os.environ, {"PATH": "\\" + folder.name}):
                self.assertIsNone(host_tool("docker"))
        finally:
            (folder / "docker.exe").unlink()
            folder.rmdir()

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
        with self.assertRaisesRegex(ValueError, "not valid UTF-8"):
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
        with patch("isolated_runner.host_tool", return_value="/abs/docker"):
            command = docker_command("info")
        self.assertEqual(command[0], "/abs/docker")
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

    def test_paths_with_spaces_stage_at_the_committed_path(self):
        """Mutation testing: a path must be split only at "/", never at whitespace."""
        files = {"dir name/file name.txt": b"spaced\n", "top level.txt": b"top\n"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, files)
            stage_source(source, root / "staged", revision)
            for name, payload in files.items():
                self.assertEqual((root / "staged" / name).read_bytes(), payload)

    def test_staged_files_keep_the_committed_modes(self):
        """Mutation testing: nothing checked the staged file modes or Git's filemode."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = fixture_repository(root, {"run.sh": b"#!/bin/sh\n", "data.txt": b"x\n"})
            git_in(source, "update-index", "--chmod=+x", "run.sh")
            git_in(source, "commit", "-qm", "executable")
            revision = git_in(source, "rev-parse", "HEAD")
            stage_source(source, root / "staged", revision)
            config = (root / "staged/.git/config").read_text(encoding="utf-8")
            self.assertIn(f"filemode = {'false' if os.name == 'nt' else 'true'}\n", config)
            if os.name != "nt":  # Windows has no executable bit
                self.assertEqual(stat.S_IMODE((root / "staged/run.sh").stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE((root / "staged/data.txt").stat().st_mode), 0o644)

    def test_only_object_files_reach_the_staged_object_store(self):
        """Mutation testing: other files in the object store must stay behind."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"a.txt": b"a\n"})
            objects = source / ".git/objects"
            for stray in ("info/stray", "pack/notes.txt"):
                (objects / stray).parent.mkdir(exist_ok=True)
                (objects / stray).write_text("not an object\n", encoding="utf-8")
            stage_source(source, root / "staged", revision)
            staged = root / "staged/.git/objects"
            copied = {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()}
            self.assertTrue(copied)
            self.assertFalse({"info/stray", "pack/notes.txt"} & copied)

    def test_filters_from_host_git_configuration_never_run_while_staging(self):
        """Mutation testing: the staged index reset must not read the host user's global
        configuration, where a filter that the commit's .gitattributes names would run."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker, home = root / "filter-ran", root / "home"
            home.mkdir()
            script = root / "probe_filter.py"
            script.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[1]).touch()\n"
                "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
                encoding="utf-8",
            )
            quoted = " ".join(
                f'"{Path(item).as_posix()}"' for item in (sys.executable, script, marker)
            )
            (home / ".gitconfig").write_text(
                f'[filter "probe"]\n\tclean = {quoted}\n', encoding="utf-8"
            )
            files = {".gitattributes": b"* filter=probe\n", "a.txt": b"a\n"}
            source, revision = fixture_repository(root, files)
            host = {"HOME": str(home), "XDG_CONFIG_HOME": str(root / "xdg")}
            with patch.dict(os.environ, host):
                stage_source(source, root / "staged", revision)
            self.assertFalse(marker.exists(), "a host Git filter ran during staging")
            # The probe works: the same reset with the host configuration runs it.
            (root / "staged/.git/index").unlink()
            git_in(
                root / "staged", "reset", "-q", "--mixed", revision, env=dict(os.environ, **host)
            )
            self.assertTrue(marker.exists())

    def test_source_given_as_a_subfolder_still_stages_the_whole_commit(self):
        """Review round 5 (A2, Q4): ls-tree without --full-tree listed only the subtree."""
        files = {"sub/inner.txt": b"inner\n", "top.txt": b"root\n"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, files)
            records = stage_source(source / "sub", root / "staged", revision)
            self.assertEqual([row["path"] for row in records], sorted(files))
            for name, payload in files.items():
                self.assertEqual((root / "staged" / name).read_bytes(), payload)

    def test_linked_worktree_stages_the_commit(self):
        """Review round 6: a linked worktree's own Git folder holds no objects, so the
        staged index reset failed with "Could not parse object <sha>"."""
        files = {"sub/inner.txt": b"inner\n", "top.txt": b"root\n"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, files)
            worktree = root / "worktree"
            git_in(source, "worktree", "add", "-q", "--detach", str(worktree), revision)
            staged = root / "staged"
            records = stage_source(worktree, staged, revision)
            self.assertEqual([row["path"] for row in records], sorted(files))
            for name, payload in files.items():
                self.assertEqual((staged / name).read_bytes(), payload)
            self.assertEqual(git_in(staged, "status", "--porcelain"), "")

    def test_unreadable_commit_tree_names_gits_error(self):
        """Review round 5: a failed ls-tree raised CalledProcessError without Git's message."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = fixture_repository(root, {"top.txt": b"root\n"})
            tree = git_in(source, "rev-parse", revision + "^{tree}")
            loose = source / ".git/objects" / tree[:2] / tree[2:]
            # Git writes object files read-only, and Windows refuses to delete those.
            loose.chmod(stat.S_IREAD | stat.S_IWRITE)
            loose.unlink()
            with self.assertRaisesRegex(RuntimeError, r"git exited \d+: fatal: \S"):
                stage_source(source, root / "staged", revision)

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
        """R3-2: Git honours refs/replace/ unless told not to. Review round 8: before
        Git 2.43 a configured core.useReplaceRefs=true overrode GIT_NO_REPLACE_OBJECTS
        (this host's Git is newer, so the configured case shows only on an older one)."""
        for configured in (False, True):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, revision = fixture_repository(root, {"README": b"committed\n"})
                (source / "README").write_bytes(b"replacement\n")
                git_in(source, "commit", "-qam", "other")
                other = git_in(source, "rev-parse", "HEAD")
                git_in(source, "reset", "-q", "--hard", revision)
                git_in(source, "replace", revision, other)
                if configured:
                    git_in(source, "config", "core.useReplaceRefs", "true")
                records = stage_source(source, root / "staged", revision)
                self.assertEqual((root / "staged/README").read_bytes(), b"committed\n")
                self.assertEqual(records[0]["git_blob"], blob_digest(b"committed\n"))
                status = git_in(root / "staged", "status", "--porcelain", "--untracked-files=no")
                self.assertEqual(status, "")
        env = isolated_runner.git_environment()
        self.assertEqual(
            [
                env.get(key)
                for key in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
            ],
            ["1", "core.useReplaceRefs", "false"],
        )

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

    def test_git_environment_drops_inherited_variables(self):
        inherited = {"GIT_DIR": "elsewhere", "GIT_CONFIG_PARAMETERS": "'core.fsmonitor'='x'"}
        with patch.dict(os.environ, inherited):
            plain, isolated = git_environment(), git_environment(isolated=True)
        for env in (plain, isolated):
            self.assertFalse(set(inherited) & set(env))
            self.assertEqual(
                (env["GIT_NO_REPLACE_OBJECTS"], env["GIT_TERMINAL_PROMPT"]), ("1", "0")
            )
        # The source checkout still sees the host's own Git settings (safe.directory).
        self.assertFalse({"GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"} & set(plain))
        self.assertEqual(
            (isolated["GIT_CONFIG_NOSYSTEM"], isolated["GIT_CONFIG_GLOBAL"]), ("1", os.devnull)
        )

    @unittest.skipUnless(
        sys.platform.startswith("linux") and not Path("/input").exists(),
        "reads /proc/self/status; /input must not exist on the test host",
    )
    def test_boundary_record_names_only_the_probes_that_ran(self):
        """Round 2 (R4-1): without a sentinel, no key may claim an outside-file check."""

        def no_network(*args, **kwargs):
            raise OSError("no network in this test")

        for sentinel, child_key in (
            (None, "child_inherits_env_denial"),
            ("host-only-sentinel", "child_inherits_outside_file_and_env_denial"),
        ):
            with self.subTest(sentinel=sentinel), tempfile.TemporaryDirectory() as directory:
                results = Path(directory)
                with patch.object(runner_workload.socket, "create_connection", no_network):
                    with self.assertRaisesRegex(RuntimeError, "boundary probe failed"):
                        # source_readable fails here: the host has no /input.
                        runner_workload.prove_boundary(sentinel, None, results)
                checks = json.loads((results / "boundary.json").read_text(encoding="utf-8"))
                self.assertIn(child_key, checks)
                self.assertTrue(checks[child_key])
                self.assertEqual(sentinel is not None, "outside_fixture_absent" in checks)
                if sentinel is None:
                    self.assertFalse([key for key in checks if "outside" in key])

    def test_capabilities_count_as_dropped_only_when_every_set_is_empty(self):
        """Review round 6 (A1): a non-root process has no effective capabilities whatever
        Docker granted it, so CapEff alone could not show a missing --cap-drop=ALL."""
        empty = "".join(
            f"{name}:\t0000000000000000\n"
            for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        )
        self.assertTrue(runner_workload.capabilities_dropped(empty))
        granted = empty.replace("CapBnd:\t0000000000000000", "CapBnd:\t00000000a80425fb")
        self.assertFalse(runner_workload.capabilities_dropped(granted))
        self.assertFalse(runner_workload.capabilities_dropped("CapEff:\t0000000000000000\n"))
        # Mutation testing (round 8): kernels before 4.3 list no ambient set, and an
        # ambient set that is not empty counts as granted.
        no_ambient = "".join(line + "\n" for line in empty.splitlines() if "CapAmb" not in line)
        self.assertTrue(runner_workload.capabilities_dropped(no_ambient))
        ambient = empty.replace("CapAmb:\t0000000000000000", "CapAmb:\t0000000000000400")
        self.assertFalse(runner_workload.capabilities_dropped(ambient))

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups and /proc")
    def test_a_workload_step_leaves_no_process_running(self):
        """Review round 6 (A2): a step's background process ran on into later steps,
        their timings and the results folder."""

        def running(pid):
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
            except (OSError, IndexError):
                return False
            return state != "Z"  # a killed orphan may wait to be reaped

        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            pidfile = results / "background.pid"
            # Absolute programs: a suite may run with a PATH that holds only git.
            sleeper = f'"{sys.executable}" -c "import time; time.sleep(60)"'
            script = f'{sleeper} & echo $! > "{pidfile}"; exit 0'
            result = runner_workload.execute(
                "leftover", ["/bin/sh", "-c", script], directory, results, timeout=60
            )
            pid = int(pidfile.read_text())
            try:
                deadline = time.monotonic() + 5
                while running(pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(result["exit"], 0)
                self.assertFalse(running(pid), "the step's background process still runs")
            finally:
                if running(pid):
                    os.kill(pid, 9)

    @unittest.skipUnless(sys.platform.startswith("linux"), "sessions and /proc")
    def test_a_process_in_its_own_group_does_not_outlive_its_step(self):
        """Review round 7: killing the step's process group missed a process that made
        its own group in the same session (GNU timeout, a shell with job control)."""
        child = (
            "import os, sys, time\n"
            "if os.fork() == 0:\n"
            "    os.setpgid(0, 0)\n"
            "    open(sys.argv[1], 'w').write(str(os.getpid()))\n"
            "    time.sleep(60)\n"
            "    os._exit(0)\n"
            "time.sleep(0.3)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results"
            results.mkdir()
            pidfile = Path(directory) / "grouped.pid"
            runner_workload.execute(
                "grouped", [sys.executable, "-c", child, str(pidfile)], directory, results, 60
            )
            pid = int(pidfile.read_text())
            try:
                deadline = time.monotonic() + 5
                while self.process_runs(pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(self.process_runs(pid), "the step's grouped process still runs")
            finally:
                if self.process_runs(pid):
                    os.kill(pid, 9)

    @unittest.skipUnless(sys.platform.startswith("linux"), "sessions, threads and /proc")
    def test_a_process_whose_main_thread_exited_does_not_outlive_its_step(self):
        """Review round 8 (W2): when a process's main thread exits while another thread
        runs, /proc shows its leader as a zombie, so the session scan passed it over."""
        child = (
            "import ctypes, os, sys, threading, time\n"
            "if os.fork() == 0:\n"
            "    os.setpgid(0, 0)\n"
            "    threading.Thread(target=time.sleep, args=(60,)).start()\n"
            "    open(sys.argv[1], 'w').write(str(os.getpid()))\n"
            "    ctypes.CDLL(None).pthread_exit(None)\n"
            "time.sleep(0.3)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results"
            results.mkdir()
            pidfile = Path(directory) / "threaded.pid"
            runner_workload.execute(
                "threaded", [sys.executable, "-c", child, str(pidfile)], directory, results, 60
            )
            pid = int(pidfile.read_text())

            def threads_run():
                try:
                    tasks = os.listdir(f"/proc/{pid}/task")
                except OSError:
                    return False
                return any(self.process_runs(f"{pid}/task/{task}") for task in tasks)

            try:
                deadline = time.monotonic() + 5
                while threads_run() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(threads_run(), "the step's threaded process still runs")
            finally:
                if threads_run():
                    os.kill(pid, 9)

    @staticmethod
    def process_runs(pid):
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            return False
        return state not in ("Z", "X")

    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and hasattr(os, "geteuid")
        and os.geteuid() == 0
        and shutil.which("unshare"),
        "needs root and unshare for a PID namespace",
    )
    def test_container_init_stops_and_reaps_every_leftover(self):
        """Review round 7 (F2, W2): a process in its own group (set -m, setpgid) or
        session survived the step's killpg, and killed orphans stayed zombies of PID 1."""
        driver = (
            "import os, sys, time; from pathlib import Path; sys.path.insert(0, sys.argv[1]);"
            " import runner_workload as rw; assert os.getpid() == 1; rw.CONTAINER_INIT = True;"
            " r = Path(sys.argv[2]);"
            " rw.execute('leftovers', ['/bin/bash', '-c', 'sleep 300 & set -m; sleep 301 &"
            " setsid sleep 302 & sleep 0.2'], r, r, timeout=30); time.sleep(0.3);"
            " print(sorted(p for p in os.listdir('/proc') if p.isdigit() and p != '1'))"
        )
        probe = ["unshare", "--pid", "--fork", "--mount-proc", sys.executable, "-c", "0"]
        if subprocess.run(probe, capture_output=True, timeout=60, check=False).returncode:
            self.skipTest("no PID namespace here (unshare needs CAP_SYS_ADMIN)")
        with tempfile.TemporaryDirectory() as directory:
            run = subprocess.run(
                [
                    "unshare",
                    "--pid",
                    "--fork",
                    "--mount-proc",
                    sys.executable,
                    "-I",
                    "-c",
                    driver,
                    str(Path(__file__).resolve().parent),
                    directory,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        self.assertEqual(run.stdout.strip().splitlines()[-1:], ["[]"], run.stderr)

    def test_windows_host_skips_probes_that_mean_nothing_in_the_container(self):
        """R3-4: a Windows path or PID names nothing inside the Linux container."""
        sentinel = Path("out") / "host-only-sentinel"
        self.assertEqual(
            isolated_runner.boundary_arguments(sentinel, 4242, windows=False),
            ["--sentinel", str(sentinel), "--host-pid", "4242"],
        )
        self.assertEqual(isolated_runner.boundary_arguments(sentinel, 4242, windows=True), [])
        for partial in ((sentinel, None), (None, 4242)):
            self.assertEqual(isolated_runner.boundary_arguments(*partial, windows=False), [])
        with patch("isolated_runner.host_tool", side_effect=docker_anywhere):
            command = execution_command(
                "sha256:" + "0" * 64, ".", ".", ".", None, None, 65534, 65534
            )
        self.assertNotIn("--sentinel", command)
        self.assertNotIn("--host-pid", command)


def git_output(*items):
    """Fake ``git cat-file --batch`` output from (digest, payload) pairs."""
    return b"".join(f"{d} blob {len(p)}\n".encode() + p + b"\n" for d, p in items)


class RunnerBranchTests(unittest.TestCase):
    """Error paths that the end-to-end tests do not reach (coverage, profile rule 20)."""

    def test_failed_command_names_the_program_and_its_error(self):
        script = "import sys; sys.stderr.write('broken'); raise SystemExit(3)"
        with self.assertRaises(RuntimeError) as caught:
            checked([sys.executable, "-c", script])
        self.assertEqual(str(caught.exception), f"{Path(sys.executable).name} exited 3: broken")

    def test_program_output_is_read_as_utf8_with_bad_bytes_replaced(self):
        """Mutation testing (round 8): no test fed checked() bytes that are not UTF-8, or
        UTF-8 that the host's locale encoding (cp1252 on Windows) reads differently."""
        script = "import sys; sys.stdout.buffer.write(b'caf\\xc3\\xa9 \\xff')"
        self.assertEqual(checked([sys.executable, "-c", script]), "café �")

    def test_bounded_helper_returns_the_program_and_both_outputs(self):
        argv = [
            sys.executable,
            "-c",
            "import sys; print('out'); sys.stderr.write('err'); sys.exit(4)",
        ]
        result = isolated_runner.run_captured(argv, timeout=60)
        self.assertEqual(
            (result.args, result.returncode, result.stdout.strip(), result.stderr),
            (argv, 4, b"out", b"err"),
        )

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
            with self.assertRaisesRegex(RuntimeError, "log reader failed") as caught:
                run_bounded([sys.executable, "-c", "pass"], timeout=30)
        self.assertIsInstance(caught.exception.__cause__, OSError)

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
            "missing or not a blob(?# non-ASCII header)": subprocess.CompletedProcess(
                [], 0, git_output((digest, good)).replace(b" blob ", b" bl\xffb ", 1), b""
            ),
        }
        for message, result in cases.items():
            with self.subTest(message=message):
                with patch("isolated_runner.run_captured", return_value=result):
                    with self.assertRaisesRegex((RuntimeError, ValueError), message):
                        read_blobs(Path("."), [digest])

    def test_git_older_than_2_32_is_refused_before_staging(self):
        """Review round 7: Git before 2.32 ignores GIT_CONFIG_GLOBAL, so the staged
        index would be built with the host user's global configuration (and Git
        before 2.31 misreads --path-format); the README's floor was not enforced."""
        versions = {
            "git version 2.31.8": False,
            "git version 1.8.3.1": False,
            "git version 2.32.0": True,
            "git version 2.56.0.windows.4": True,
            "git version 2.39.3 (Apple Git-145)": True,
            "git version 3.0.0": True,
            "not git": False,
        }
        for text, accepted in versions.items():
            with self.subTest(version=text):
                with patch("isolated_runner.checked", return_value=text):
                    if accepted:
                        isolated_runner.require_git()
                    else:
                        with self.assertRaisesRegex(RuntimeError, "Git 2.32 or later"):
                            isolated_runner.require_git()
        with tempfile.TemporaryDirectory() as directory:
            with patch("isolated_runner.checked", return_value="git version 2.31.0"):
                with self.assertRaisesRegex(RuntimeError, "Git 2.32 or later"):
                    stage_source(Path(directory), Path(directory) / "staged", "a" * 40)
            self.assertFalse((Path(directory) / "staged").exists())

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
        row = json.dumps(record, ensure_ascii=False)  # non-ASCII text stays raw
        (self.root / "ledger.jsonl").write_text(row + "\n", encoding="utf-8")

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

    def test_ledger_row_with_a_raw_line_separator_in_a_string_is_one_record(self):
        """Review round 6 (D1): str.splitlines also splits at U+2028, U+2029 and U+0085,
        which JSON allows unescaped inside a string, so a valid row failed the gate."""
        for separator in ("\u2028", "\u2029", "\x85"):
            with self.subTest(separator=hex(ord(separator))):
                self.ledger(note=f"a{separator}b")
                before = semantic_hash(self.root)
                self.ledger(note=f"a{separator}c")
                self.assertNotEqual(before, semantic_hash(self.root))

    def test_a_carriage_return_never_ends_a_ledger_row(self):
        """Review round 7: reading as text turned a lone CR into a line feed, so CR as
        JSON whitespace split a valid row and a lone CR ended one."""
        (self.root / "ledger.jsonl").write_bytes(b'{"a":\r1}\r\n{"b":2}\n')
        semantic_hash(self.root)
        (self.root / "ledger.jsonl").write_bytes(b'{"a":1}\r{"b":2}\n')
        with self.assertRaises(ValueError):
            semantic_hash(self.root)

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

    def test_each_kind_of_output_is_compared_as_documented(self):
        """Mutation testing (round 8): no test spelled out the manifest, so a changed
        comparison for one kind of file (CSV, text, JSON key order, a nested folder)
        went unseen. Every expected value here is written out independently."""
        root = str(self.root)
        (self.root / "metrics.json").write_text(
            json.dumps({"b": [root + "/x", {"created_at": 1, "v": 2}], "a": 1}), encoding="utf-8"
        )
        (self.root / "rows.jsonl").write_text(
            json.dumps({"z": 1, "y": 2, "recorded_at": 5})
            + "\n\n"
            + json.dumps({"a": root})
            + "\n",
            encoding="utf-8",
        )
        self.compressed(b"v\n1\n")
        (self.root / "plain.csv").write_bytes(root.encode() + b",1\n")
        for suffix in (".html", ".md", ".txt", ".yaml", ".yml"):
            (self.root / f"note{suffix}").write_text(f"at {root}\n", encoding="utf-8")
        (self.root / "data.bin").write_bytes(root.encode())
        (self.root / "sub").mkdir()
        (self.root / "sub" / "inner.json").write_text('{"k": "v"}', encoding="utf-8")

        def row(path, comparison, payload):
            digest = hashlib.sha256(payload).hexdigest()
            return {"path": str(Path(path)), "comparison": comparison, "sha256": digest}

        text = "UTF-8 text; output root normalized"
        json_kind = "json; declared volatile keys and output root normalized"
        expected = {
            "version": 2,
            "volatile_json_keys": ["created_at", "created_utc", "recorded_at", "retrieved_at"],
            "records": [
                row("data.bin", "raw bytes; no undeclared exclusion", root.encode()),
                row("metrics.json", json_kind, b'{"a": 1, "b": ["$RUN/x", {"v": 2}]}'),
                row("note.html", text, b"at $RUN\n"),
                row("note.md", text, b"at $RUN\n"),
                row("note.txt", text, b"at $RUN\n"),
                row("note.yaml", text, b"at $RUN\n"),
                row("note.yml", text, b"at $RUN\n"),
                row("plain.csv", "CSV bytes", root.encode() + b",1\n"),
                row(
                    "rows.jsonl",
                    "jsonl; record order retained; declared volatile keys normalized",
                    b'[{"y": 2, "z": 1}, {"a": "$RUN"}]',
                ),
                row("sub/inner.json", json_kind, b'{"k": "v"}'),
                row(
                    "table.csv.gz",
                    "decompressed CSV bytes; gzip header metadata excluded",
                    b"v\n1\n",
                ),
            ],
            "figures_present_nonempty": ["figure.png"],
            "figure_byte_comparison": "excluded; source tables participate in the gate",
        }
        self.assertEqual(semantic_manifest(self.root), expected)

    def test_json_nested_too_deeply_fails_the_gate_with_a_reason(self):
        """Review round 10: a JSON or JSONL output nested past the recursion limit raised
        RecursionError, which main's gate handler (ValueError, OSError) does not catch,
        so the workload stopped with a traceback and no benchmark summary."""
        deep = "[" * 100000 + "]" * 100000
        for name in ("metrics.json", "rows.jsonl"):
            with self.subTest(name=name):
                (self.root / "metrics.json").write_text("{}", encoding="utf-8")
                (self.root / name).write_text(deep + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, f"^JSON nested too deeply: {name}$"):
                    semantic_manifest(self.root)
                (self.root / name).unlink()
        (self.root / "metrics.json").write_text("[[[1]]]", encoding="utf-8")
        semantic_manifest(self.root)

    def test_records_and_a_nonempty_figure_are_both_required(self):
        (self.root / "figure.png").unlink()
        with self.assertRaisesRegex(
            ValueError, "^Workflow produced no semantic records or figures$"
        ):
            semantic_manifest(self.root)
        (self.root / "metrics.json").unlink()
        (self.root / "figure.png").write_bytes(b"x")
        with self.assertRaisesRegex(
            ValueError, "^Workflow produced no semantic records or figures$"
        ):
            semantic_manifest(self.root)
        (self.root / "metrics.json").write_text("{}", encoding="utf-8")
        (self.root / "figure.png").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "^Empty figure$"):
            semantic_manifest(self.root)


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
