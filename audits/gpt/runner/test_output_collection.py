import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from output_collection import (
    SUMMARY_NAMES,
    CollectionLimits,
    RejectedOutput,
    collect_results,
    collect_workload,
    read_summaries,
)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "Linux/POSIX collector")
class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.produced = self.work / "results"
        self.produced.mkdir(parents=True)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.destination = self.evidence / "workload"
        self.canary = self.root / "host-only-canary"
        self.marker = b"NON_SECRET_OUTSIDE_FIXTURE"
        self.canary.write_bytes(self.marker)

    def rejected(self, **kwargs):
        with self.assertRaises(RejectedOutput):
            collect_results(self.work, self.destination, **kwargs)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.evidence.iterdir()), [])
        self.assertEqual(self.canary.read_bytes(), self.marker)

    def test_regular_files_and_empty_directories_are_preserved(self):
        (self.produced / "nested").mkdir()
        (self.produced / "empty").mkdir()
        payload = b"ordinary output\n"
        (self.produced / "nested/table.csv").write_bytes(payload)
        for name in SUMMARY_NAMES:
            (self.produced / name).write_text('{"ok":true}')
        result = collect_results(self.work, self.destination)
        self.assertEqual(result["status"], "collected")
        self.assertEqual((self.destination / "nested/table.csv").read_bytes(), payload)
        self.assertTrue((self.destination / "empty").is_dir())
        row = next(x for x in result["files"] if x["path"] == "nested/table.csv")
        self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(set(result["summaries"]), set(SUMMARY_NAMES))

    def test_previous_copy_primitive_leaks_only_the_generated_control(self):
        (self.produced / "escape").symlink_to(self.canary)
        copied = self.root / "old-copy-control"
        shutil.copytree(self.produced, copied)
        self.assertEqual((copied / "escape").read_bytes(), self.marker)
        self.rejected()

    def test_file_symlink_is_rejected(self):
        (self.produced / "escape").symlink_to(self.canary)
        self.rejected()

    def test_directory_symlink_is_rejected(self):
        (self.produced / "escape").symlink_to(self.root, target_is_directory=True)
        self.rejected()

    def test_results_root_symlink_is_rejected(self):
        self.produced.rmdir()
        self.produced.symlink_to(self.root, target_is_directory=True)
        self.rejected()

    def test_work_root_symlink_is_rejected(self):
        replacement = self.root / "replacement"
        self.work.rename(replacement)
        self.work.symlink_to(replacement, target_is_directory=True)
        self.rejected()

    def test_dangling_symlink_is_rejected(self):
        (self.produced / "escape").symlink_to(self.root / "missing")
        self.rejected()

    def test_internal_symlink_is_also_rejected(self):
        (self.produced / "real").write_text("ordinary")
        (self.produced / "alias").symlink_to("real")
        self.rejected()

    def test_all_summary_link_sinks_fail_without_logging_canary(self):
        for name in SUMMARY_NAMES:
            with self.subTest(name=name):
                link = self.produced / name
                link.symlink_to(self.canary)
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    result = collect_workload(self.work, self.evidence)
                self.assertEqual(result["status"], "rejected")
                self.assertFalse(self.destination.exists())
                self.assertNotIn(self.marker.decode(), captured.getvalue())
                self.assertNotIn(self.marker, (self.evidence / "collection.json").read_bytes())
                self.assertFalse(any(p.is_symlink() for p in self.evidence.rglob("*")))
                (self.evidence / "collection.json").unlink()
                link.unlink()

    def test_direct_summary_reader_rejects_each_link(self):
        for name in SUMMARY_NAMES:
            with self.subTest(name=name):
                link = self.produced / name
                link.symlink_to(self.canary)
                with self.assertRaises(RejectedOutput):
                    read_summaries(self.produced)
                link.unlink()

    def test_hard_link_is_rejected(self):
        os.link(self.canary, self.produced / "escape")
        self.rejected()

    def test_fifo_is_rejected_without_opening_it(self):
        os.mkfifo(self.produced / "pipe")
        self.rejected()

    def test_socket_is_rejected(self):
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(self.produced / "socket"))
            self.rejected()

    def test_missing_results_are_rejected(self):
        self.produced.rmdir()
        self.rejected()

    def test_file_size_limit_is_enforced(self):
        (self.produced / "large").write_bytes(b"12345")
        self.rejected(limits=CollectionLimits(file_bytes=4))

    def test_total_size_limit_is_enforced_atomically(self):
        (self.produced / "one").write_bytes(b"1234")
        (self.produced / "two").write_bytes(b"5678")
        self.rejected(limits=CollectionLimits(total_bytes=7))

    def test_entry_count_limit_includes_empty_directories(self):
        (self.produced / "one").mkdir()
        (self.produced / "two").mkdir()
        self.rejected(limits=CollectionLimits(entries=1))

    def test_directory_depth_limit_is_enforced(self):
        (self.produced / "one/two").mkdir(parents=True)
        self.rejected(limits=CollectionLimits(depth=1))

    def test_invalid_or_nonobject_summary_is_rejected(self):
        for text in (
            "not-json",
            "[]",
            '{"value":NaN}',
            '{"deep":' + "[" * 2000 + "0" + "]" * 2000 + "}",
            json.dumps({"nodes": [0] * 4097}),
        ):
            with self.subTest(text=text):
                (self.produced / "boundary.json").write_text(text)
                self.rejected()

    def test_summary_limit_is_enforced(self):
        (self.produced / "boundary.json").write_text(json.dumps({"large": "x" * 65536}))
        self.rejected()

    def test_summary_workflow_commands_are_escaped(self):
        (self.produced / "boundary.json").write_text(
            json.dumps({"note": "ok\n::error::untrusted command ##[error]older form"})
        )
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            report = collect_workload(self.work, self.evidence)
        self.assertEqual(report["status"], "collected")
        lines = captured.getvalue().splitlines()
        self.assertFalse(any(line.lstrip().startswith("::") or "##[" in line for line in lines))

    def test_file_replaced_by_link_between_stat_and_open_is_rejected(self):
        target = self.produced / "replace-me"
        target.write_text("safe")
        real_open = os.open

        def switched(path, flags, *args, **kwargs):
            if path == "replace-me":
                target.unlink()
                target.symlink_to(self.canary)
            return real_open(path, flags, *args, **kwargs)

        with patch("output_collection.os.open", side_effect=switched):
            self.rejected()

    def test_directory_replaced_by_link_between_stat_and_open_is_rejected(self):
        target = self.produced / "replace-me"
        target.mkdir()
        real_open = os.open

        def switched(path, flags, *args, **kwargs):
            if path == "replace-me":
                target.rmdir()
                target.symlink_to(self.root, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)

        with patch("output_collection.os.open", side_effect=switched):
            self.rejected()

    def test_destination_inside_work_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            collect_results(self.work, self.work / "copy")

    def test_destination_through_a_link_in_work_is_refused(self):
        (self.work / "outside").symlink_to(self.evidence, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside"):
            collect_results(self.work, self.work / "outside/copy")

    def test_unsafe_archive_filenames_are_rejected(self):
        for name in ("..\\outside", "drive:C", "line\nbreak", "tab\tname", "wild?card"):
            with self.subTest(name=name):
                path = self.produced / name
                path.write_text("ordinary generated content")
                self.rejected()
                path.unlink()

    def test_existing_destination_is_preserved(self):
        self.destination.mkdir()
        (self.destination / "keep").write_text("previous evidence")
        with self.assertRaisesRegex(ValueError, "already exists"):
            collect_results(self.work, self.destination)
        self.assertEqual((self.destination / "keep").read_text(), "previous evidence")


if __name__ == "__main__":
    unittest.main()
