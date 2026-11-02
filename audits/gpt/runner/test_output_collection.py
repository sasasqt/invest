"""Collector tests, run against both walks: descriptors (POSIX) and paths (all hosts)."""

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
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("CONTRACT_CHECKS", "1")

from output_collection import (
    DEFAULT_METHOD,
    DESCRIPTOR_APIS,
    SUMMARY_NAMES,
    CollectionLimits,
    RejectedOutput,
    collect_results,
    collect_workload,
    portable_name,
    read_summaries,
)

POSIX_ONLY = unittest.skipUnless(os.name == "posix", "POSIX file types and names")


class NameTests(unittest.TestCase):
    def test_portable_names_are_accepted(self):
        for name in ("table.csv", "boundary.json", ".hidden", "a b", "CONSOLE", "con-1", "Ünïcode"):
            with self.subTest(name=name):
                self.assertTrue(portable_name(name))

    def test_names_windows_or_zip_would_read_differently_are_rejected(self):
        names = ["", ".", "..", "a\\b", "a/b", "c:d", "x*", "q?", 'quote"', "<", ">", "pipe|"]
        names += ["line\nbreak", "tab\tname", "del\x7f", "trailing.", "trailing ", "CON", "nul"]
        names += ["Aux.txt", "com1", "LPT9.tar.gz", "COM\u00b9", "conin$", "CON .txt", "bad\udcff"]
        for name in names:
            with self.subTest(name=name):
                self.assertFalse(portable_name(name))

    def test_default_walk_matches_the_host(self):
        self.assertEqual(DEFAULT_METHOD, "descriptor" if DESCRIPTOR_APIS else "path")
        if os.name == "nt":
            self.assertEqual(DEFAULT_METHOD, "path")


class CollectionCases:
    method = None

    def collect(self, **kwargs):
        return collect_results(self.work, self.destination, method=self.method, **kwargs)

    def link(self, path, target, directory=False):
        """Create a symbolic link, or skip where Windows withholds the privilege."""
        try:
            path.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f"symbolic links unavailable: {exc}")

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
            self.collect(**kwargs)
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
        result = self.collect()
        self.assertEqual(result["status"], "collected")
        self.assertEqual((self.destination / "nested/table.csv").read_bytes(), payload)
        self.assertTrue((self.destination / "empty").is_dir())
        row = next(x for x in result["files"] if x["path"] == "nested/table.csv")
        self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(set(result["summaries"]), set(SUMMARY_NAMES))

    def test_previous_copy_primitive_leaks_only_the_generated_control(self):
        self.link(self.produced / "escape", self.canary)
        copied = self.root / "old-copy-control"
        shutil.copytree(self.produced, copied)
        self.assertEqual((copied / "escape").read_bytes(), self.marker)
        self.rejected()

    def test_file_symlink_is_rejected(self):
        self.link(self.produced / "escape", self.canary)
        self.rejected()

    def test_directory_symlink_is_rejected(self):
        self.link(self.produced / "escape", self.root, directory=True)
        self.rejected()

    def test_results_root_symlink_is_rejected(self):
        self.produced.rmdir()
        self.link(self.produced, self.root, directory=True)
        self.rejected()

    def test_work_root_symlink_is_rejected(self):
        replacement = self.root / "replacement"
        self.work.rename(replacement)
        self.link(self.work, replacement, directory=True)
        self.rejected()

    def test_dangling_symlink_is_rejected(self):
        self.link(self.produced / "escape", self.root / "missing")
        self.rejected()

    def test_internal_symlink_is_also_rejected(self):
        (self.produced / "real").write_text("ordinary")
        self.link(self.produced / "alias", "real")
        self.rejected()

    def test_all_summary_link_sinks_fail_without_logging_canary(self):
        for name in SUMMARY_NAMES:
            with self.subTest(name=name):
                link = self.produced / name
                self.link(link, self.canary)
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    result = collect_workload(self.work, self.evidence, method=self.method)
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
                self.link(link, self.canary)
                with self.assertRaises(RejectedOutput):
                    read_summaries(self.produced, self.method)
                link.unlink()

    def test_hard_link_is_rejected(self):
        os.link(self.canary, self.produced / "escape")
        self.rejected()

    @POSIX_ONLY
    def test_fifo_is_rejected_without_opening_it(self):
        os.mkfifo(self.produced / "pipe")
        self.rejected()

    @unittest.skipUnless(hasattr(socket, "AF_UNIX") and os.name == "posix", "POSIX sockets")
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
            report = collect_workload(self.work, self.evidence, method=self.method)
        self.assertEqual(report["status"], "collected")
        lines = captured.getvalue().splitlines()
        self.assertFalse(any(line.lstrip().startswith("::") or "##[" in line for line in lines))

    def test_file_replaced_by_link_between_stat_and_open_is_rejected(self):
        target = self.produced / "replace-me"
        target.write_text("safe")
        real_open = os.open
        self.link(self.root / "probe", self.canary)

        def switched(path, flags, *args, **kwargs):
            if os.path.basename(path) == "replace-me":
                target.unlink()
                target.symlink_to(self.canary)
            return real_open(path, flags, *args, **kwargs)

        with patch("output_collection.os.open", side_effect=switched):
            self.rejected()

    def test_directory_replaced_by_link_between_stat_and_open_is_rejected(self):
        target = self.produced / "replace-me"
        target.mkdir()
        self.link(self.root / "probe", self.root, directory=True)
        # The descriptor walk opens the folder; the path walk lists it.
        name = "open" if self.method == "descriptor" else "scandir"
        real = getattr(os, name)

        def switched(path, *args, **kwargs):
            if isinstance(path, str) and os.path.basename(path) == "replace-me":
                target.rmdir()
                target.symlink_to(self.root, target_is_directory=True)
            return real(path, *args, **kwargs)

        with patch(f"output_collection.os.{name}", side_effect=switched):
            self.rejected()

    def test_directory_replaced_by_another_directory_is_rejected(self):
        target = self.produced / "replace-me"
        target.mkdir()
        # The descriptor walk opens the folder; the path walk lists it.
        name = "open" if self.method == "descriptor" else "scandir"
        real = getattr(os, name)

        def switched(path, *args, **kwargs):
            if isinstance(path, str) and os.path.basename(path) == "replace-me":
                target.rename(self.work / "moved")
                target.mkdir()
            return real(path, *args, **kwargs)

        with patch(f"output_collection.os.{name}", side_effect=switched):
            self.rejected()

    def test_file_growing_while_it_is_read_is_rejected(self):
        source = self.produced / "growing.log"
        source.write_bytes(b"first part\n")
        real_read, grown = os.read, []

        def growing(fd, size):
            data = real_read(fd, size)
            if data and not grown:
                grown.append(True)
                with source.open("ab") as stream:
                    stream.write(b"appended while the host was copying\n")
            return data

        with patch("output_collection.os.read", side_effect=growing):
            self.rejected()

    def test_unknown_method_and_non_positive_limits_are_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown collection method"):
            collect_results(self.work, self.destination, method="copytree")
        with self.assertRaisesRegex(ValueError, "positive"):
            self.collect(limits=CollectionLimits(entries=0))
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_interrupt_during_collection_leaves_no_snapshot(self):
        (self.produced / "file").write_text("ordinary")
        with patch("output_collection.copy_tree", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.collect()
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_destination_inside_work_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            collect_results(self.work, self.work / "copy")

    def test_destination_through_a_link_in_work_is_refused(self):
        self.link(self.work / "outside", self.evidence, directory=True)
        with self.assertRaisesRegex(ValueError, "outside"):
            collect_results(self.work, self.work / "outside/copy")

    @POSIX_ONLY
    def test_unsafe_archive_filenames_are_rejected(self):
        names = ("..\\outside", "drive:C", "line\nbreak", "tab\tname", "wild?card")
        names += ("trailing.", "trailing ", "CON", "nul.txt", "COM1.log")
        for name in names:
            with self.subTest(name=name):
                path = self.produced / name
                path.write_text("ordinary generated content")
                self.rejected()
                path.unlink()

    def test_existing_destination_is_preserved(self):
        self.destination.mkdir()
        (self.destination / "keep").write_text("previous evidence")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.collect()
        self.assertEqual((self.destination / "keep").read_text(), "previous evidence")

    @POSIX_ONLY
    def test_non_utf8_name_is_rejected(self):
        """Finding F4: the artifact upload cannot name a file whose bytes are not UTF-8."""
        fd = os.open(os.fsencode(self.produced) + b"/bad-\xff-name", os.O_CREAT | os.O_WRONLY)
        os.close(fd)
        self.rejected()

    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_junction_is_rejected(self):
        import _winapi

        outside = self.root / "outside"
        outside.mkdir()
        (outside / "canary").write_bytes(self.marker)
        _winapi.CreateJunction(str(outside), str(self.produced / "junction"))
        self.rejected()

    def test_binary_bytes_are_copied_exactly(self):
        payload = b"line\r\nnext\n\x1a\x00tail"
        (self.produced / "binary.bin").write_bytes(payload)
        result = self.collect()
        self.assertEqual((self.destination / "binary.bin").read_bytes(), payload)
        self.assertEqual(result["files"][0]["sha256"], hashlib.sha256(payload).hexdigest())


@unittest.skipUnless(DESCRIPTOR_APIS, "POSIX descriptor walk")
class DescriptorCollectionTests(CollectionCases, unittest.TestCase):
    method = "descriptor"


@unittest.skipIf(DESCRIPTOR_APIS, "descriptor APIs present")
class NoDescriptorTests(unittest.TestCase):
    def test_descriptor_walk_fails_closed_without_its_apis(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory, "work")
            (work / "results").mkdir(parents=True)
            with self.assertRaisesRegex(RejectedOutput, "descriptor-based collection unavailable"):
                collect_results(work, Path(directory, "evidence/workload"), method="descriptor")


class PathCollectionTests(CollectionCases, unittest.TestCase):
    method = "path"

    def stale_lstat(self, change):
        """Python 3.13 on Windows can stat by name from the folder entry, whose times and
        size may lag the open handle's; only the file ID must match."""
        real = os.lstat

        def lstat(path, *args, **kwargs):
            info = real(path, *args, **kwargs)
            if os.path.basename(path) != "table.csv":
                return info
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            return SimpleNamespace(**dict(fields, **change(info)))

        return patch("output_collection.os.lstat", side_effect=lstat)

    def test_stale_times_and_size_in_a_by_name_stat_are_tolerated(self):
        (self.produced / "table.csv").write_bytes(b"ordinary output\n")
        older = {"st_mtime_ns": 1, "st_ctime_ns": 2, "st_size": 3}
        with self.stale_lstat(lambda info: older):
            result = self.collect()
        self.assertEqual(result["files"][0]["bytes"], len(b"ordinary output\n"))

    def test_results_folder_replaced_while_listed_is_rejected(self):
        real = os.scandir

        def switched(path, *args, **kwargs):
            if isinstance(path, str) and os.path.basename(path) == "results":
                self.produced.rename(self.work / "results-before")
                self.produced.mkdir()
            return real(path, *args, **kwargs)

        with patch("output_collection.os.scandir", side_effect=switched):
            self.rejected()

    @POSIX_ONLY
    def test_parent_replaced_by_link_before_a_file_open_is_rejected(self):
        folder = self.produced / "sub"
        folder.mkdir()
        (folder / "file").write_bytes(b"ordinary")
        real, swapped = os.lstat, []

        def lstat(path, *args, **kwargs):
            if not swapped and os.path.basename(path) == "file":
                swapped.append(True)
                folder.rename(self.work / "sub-real")
                folder.symlink_to(self.work / "sub-real", target_is_directory=True)
            return real(path, *args, **kwargs)

        with patch("output_collection.os.lstat", side_effect=lstat):
            self.rejected()
        self.assertTrue(swapped)

    def test_a_different_file_id_at_open_is_rejected(self):
        (self.produced / "table.csv").write_bytes(b"ordinary output\n")
        with self.stale_lstat(lambda info: {"st_ino": info.st_ino + 1}):
            self.rejected()


if __name__ == "__main__":
    unittest.main()
