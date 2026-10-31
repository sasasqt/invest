import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ci_evidence import classify
from isolated_runner import execution_command, stage_source
from runner_workload import semantic_hash
from verify_installed import applicable_requirements, verify_versions
from verify_snapshot import SnapshotError, verify


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
