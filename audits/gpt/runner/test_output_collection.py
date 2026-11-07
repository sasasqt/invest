"""Collector tests, run against both walks: descriptors (POSIX) and paths (all hosts)."""

import contextlib
import errno
import hashlib
import io
import json
import os
import shutil
import socket
import stat
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("CONTRACT_CHECKS", "1")

import output_collection
from contract import ContractViolation
from output_collection import (
    DEFAULT_LIMITS,
    DEFAULT_METHOD,
    DESCRIPTOR_APIS,
    SUMMARY_MAX_BYTES,
    SUMMARY_NAMES,
    CollectionLimits,
    PathFolder,
    RejectedOutput,
    check_collected,
    collect_results,
    collect_workload,
    is_link,
    log_line,
    portable_name,
    read_summaries,
)

POSIX_ONLY = unittest.skipUnless(os.name == "posix", "POSIX file types and names")
# A test of a contract check itself; with the test mode off that check never runs.
NEEDS_CHECKS = unittest.skipUnless(
    os.environ.get("CONTRACT_CHECKS") == "1", "tests a contract check (CONTRACT_CHECKS=1)"
)
LINKED = "linked, special or cross-device output entry"
MISSING = "missing, linked or unreadable output directory"


class NameTests(unittest.TestCase):
    def test_portable_names_are_accepted(self):
        names = ("table.csv", "boundary.json", ".hidden", "a b", "CONSOLE", "con-1", "Ünïcode")
        names += ("nameX", "CONX.txt", "CON\u3000.txt", "a.b.CON")
        names += ("notes~", "backup~1.toml", "LONGNAME9~1", "x~1y", "ABCDEF~12")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(portable_name(name))

    def test_names_windows_or_zip_would_read_differently_are_rejected(self):
        names = ["", ".", "..", "a\\b", "a/b", "c:d", "x*", "q?", 'quote"', "<", ">", "pipe|"]
        names += ["line\nbreak", "tab\tname", "del\x7f", "trailing.", "trailing ", "CON", "nul"]
        names += ["Aux.txt", "com1", "LPT9.tar.gz", "COM\u00b9", "conin$", "CON .txt", "bad\udcff"]
        names += ["PROGRA~1", "AAAAAA~1", "x~12.py", "AB12~3.TXT"]  # NTFS short-name forms
        for name in names:
            with self.subTest(name=name):
                self.assertFalse(portable_name(name))

    def test_every_reparse_point_counts_as_a_link(self):
        reparse = SimpleNamespace(
            st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
        plain = SimpleNamespace(
            st_mode=stat.S_IFREG, st_file_attributes=stat.FILE_ATTRIBUTE_ARCHIVE
        )
        self.assertTrue(is_link(reparse))
        self.assertFalse(is_link(plain))
        self.assertFalse(is_link(SimpleNamespace(st_mode=stat.S_IFREG)))

    def test_log_lines_are_ascii_even_for_lone_surrogates(self):
        """JSON summaries may decode to lone surrogates, which a UTF-8 stream cannot write."""
        stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        log_line("AUDIT_TEST", {"note": "\udcff caf\u00e9 \u2028"}, stream)
        stream.flush()
        line = stream.buffer.getvalue().decode("ascii")
        self.assertEqual(
            json.loads(line.removeprefix("AUDIT_TEST ")), {"note": "\udcff caf\u00e9 \u2028"}
        )

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

    def rejected(self, reason, **kwargs):
        """The collection must fail for ``reason`` (a regex), leaving nothing behind."""
        with self.assertRaisesRegex(RejectedOutput, reason):
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

    def test_file_larger_than_one_read_is_recorded_whole(self):
        payload = bytes(range(256)) * 800  # 204,800 bytes: several reads
        (self.produced / "nested").mkdir()
        (self.produced / "nested/large.bin").write_bytes(payload)
        result = self.collect()
        row = next(x for x in result["files"] if x["path"] == "nested/large.bin")
        self.assertEqual(row["bytes"], len(payload))
        self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual((self.destination / "nested/large.bin").read_bytes(), payload)
        if os.name != "nt":  # the private snapshot's folders are owner-only
            self.assertEqual(stat.S_IMODE((self.destination / "nested").stat().st_mode), 0o700)

    def test_previous_copy_primitive_leaks_only_the_generated_control(self):
        self.link(self.produced / "escape", self.canary)
        copied = self.root / "old-copy-control"
        shutil.copytree(self.produced, copied)
        self.assertEqual((copied / "escape").read_bytes(), self.marker)
        self.rejected(LINKED)

    def test_file_symlink_is_rejected(self):
        self.link(self.produced / "escape", self.canary)
        self.rejected(LINKED)

    def test_directory_symlink_is_rejected(self):
        self.link(self.produced / "escape", self.root, directory=True)
        self.rejected(LINKED)

    def test_results_root_symlink_is_rejected(self):
        self.produced.rmdir()
        self.link(self.produced, self.root, directory=True)
        self.rejected(MISSING)

    def test_work_root_symlink_is_rejected(self):
        replacement = self.root / "replacement"
        self.work.rename(replacement)
        self.link(self.work, replacement, directory=True)
        self.rejected(MISSING)

    def test_dangling_symlink_is_rejected(self):
        self.link(self.produced / "escape", self.root / "missing")
        self.rejected(LINKED)

    def test_internal_symlink_is_also_rejected(self):
        (self.produced / "real").write_text("ordinary")
        self.link(self.produced / "alias", "real")
        self.rejected(LINKED)

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

    def test_a_summary_that_grows_after_its_check_names_the_summary_limit(self):
        """Review round 12: read_opened checked the opened summary with the default
        reason, so a summary that grew past 64 KiB between its check by name and the
        open was reported as "output file size limit exceeded"."""
        (self.produced / "boundary.json").write_text("{}", encoding="utf-8")
        real = os.fstat

        def grown(fd):
            info = real(fd)
            if not stat.S_ISREG(info.st_mode):
                return info
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            return SimpleNamespace(**dict(fields, st_size=SUMMARY_MAX_BYTES + 1))

        with patch("output_collection.os.fstat", side_effect=grown):
            with self.assertRaisesRegex(RejectedOutput, "^summary size limit exceeded$"):
                read_summaries(self.produced, self.method)

    def test_an_output_file_that_grows_after_its_check_names_the_file_limit(self):
        """Mutation testing (round 12): the reason for an output file that grew past its
        limit between its check by name and the read (read_opened's default) was never
        compared, only a file that was already too large when checked."""
        (self.produced / "table.csv").write_bytes(b"123")
        real = os.fstat

        def grown(fd):
            info = real(fd)
            if not stat.S_ISREG(info.st_mode):
                return info
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            return SimpleNamespace(**dict(fields, st_size=5))

        with patch("output_collection.os.fstat", side_effect=grown):
            self.rejected(
                "^output file size limit exceeded$", limits=CollectionLimits(file_bytes=4)
            )

    def test_hard_link_is_rejected(self):
        os.link(self.canary, self.produced / "escape")
        self.rejected(LINKED)

    @POSIX_ONLY
    def test_fifo_is_rejected_without_opening_it(self):
        os.mkfifo(self.produced / "pipe")
        self.rejected(LINKED)

    @unittest.skipUnless(hasattr(socket, "AF_UNIX") and os.name == "posix", "POSIX sockets")
    def test_socket_is_rejected(self):
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(self.produced / "socket"))
            self.rejected(LINKED)

    def test_missing_results_are_rejected(self):
        self.produced.rmdir()
        self.rejected(MISSING)

    def test_file_size_limit_is_enforced(self):
        (self.produced / "large").write_bytes(b"12345")
        self.rejected("output file size limit exceeded", limits=CollectionLimits(file_bytes=4))

    def test_total_size_limit_is_enforced_atomically(self):
        (self.produced / "one").write_bytes(b"1234")
        (self.produced / "two").write_bytes(b"5678")
        self.rejected("output byte limit exceeded", limits=CollectionLimits(total_bytes=7))

    def test_entry_count_limit_includes_empty_directories(self):
        (self.produced / "one").mkdir()
        (self.produced / "two").mkdir()
        self.rejected("output entry count limit exceeded", limits=CollectionLimits(entries=1))

    def test_directory_depth_limit_is_enforced(self):
        (self.produced / "one/two").mkdir(parents=True)
        self.rejected("output directory depth limit exceeded", limits=CollectionLimits(depth=1))

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
                self.rejected("invalid JSON summary")

    def test_summary_limit_is_enforced(self):
        """Review round 11: a summary over 64 KiB but under the 16 MiB file limit was
        rejected as "output file size limit exceeded", so a reader looked for a file over
        the limit that collection.json shows."""
        (self.produced / "boundary.json").write_text(json.dumps({"large": "x" * 65536}))
        self.rejected("summary size limit exceeded")

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
            self.rejected("unreadable or changing|output file changed")

    def test_directory_replaced_by_link_between_stat_and_open_is_rejected(self):
        target = self.produced / "replace-me"
        target.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "large.bin").write_bytes(b"x" * 64)
        self.link(self.root / "probe", outside, directory=True)
        # The descriptor walk opens the folder; the path walk lists it.
        name = "open" if self.method == "descriptor" else "scandir"
        real, fired = getattr(os, name), []

        def switched(path, *args, **kwargs):
            if not fired and isinstance(path, str) and os.path.basename(path) == "replace-me":
                fired.append(path)
                target.rmdir()
                target.symlink_to(outside, target_is_directory=True)
            return real(path, *args, **kwargs)

        # The path walk must notice the link as soon as it lists the folder, before it
        # looks at any entry reached through it (here, one over the size limit).
        with patch(f"output_collection.os.{name}", side_effect=switched):
            self.rejected(
                {"descriptor": MISSING, "path": "output directory changed"}[self.method],
                limits=CollectionLimits(file_bytes=4),
            )
        self.assertTrue(fired)

    def test_directory_replaced_by_another_directory_is_rejected(self):
        target = self.produced / "replace-me"
        target.mkdir()
        # The descriptor walk opens the folder; the path walk lists it.
        name = "open" if self.method == "descriptor" else "scandir"
        real, fired = getattr(os, name), []

        def switched(path, *args, **kwargs):
            # Once only: shutil.rmtree lists folders with os.scandir on Windows too.
            if not fired and isinstance(path, str) and os.path.basename(path) == "replace-me":
                fired.append(path)
                target.rename(self.work / "moved")
                target.mkdir()
            return real(path, *args, **kwargs)

        with patch(f"output_collection.os.{name}", side_effect=switched):
            self.rejected("output directory changed during collection")
        self.assertTrue(fired)

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
            self.rejected("output file changed during collection")

    def test_output_exactly_at_each_limit_is_collected(self):
        (self.produced / "one").mkdir()
        (self.produced / "one/four").write_bytes(b"1234")
        (self.produced / "three").write_bytes(b"567")
        limits = CollectionLimits(file_bytes=4, total_bytes=7, entries=3, depth=1)
        result = self.collect(limits=limits)
        self.assertEqual((result["entries"], result["bytes"]), (3, 7))

    def test_results_that_are_a_file_are_rejected(self):
        self.produced.rmdir()
        self.produced.write_text("not a folder")
        self.rejected(MISSING)

    def test_summary_exactly_at_its_limits_is_accepted(self):
        filler = SUMMARY_MAX_BYTES - len(json.dumps({"large": ""}))
        nested = {"deep": json.loads("[" * 31 + "0" + "]" * 31)}  # deepest value at depth 32
        for value in ({"large": "x" * filler}, nested, {"nodes": [0] * 4094}):  # 4096 nodes
            with self.subTest(size=len(json.dumps(value))):
                shutil.rmtree(self.evidence)
                self.evidence.mkdir()
                (self.produced / "boundary.json").write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(self.collect()["summaries"]["boundary.json"], value)

    def test_summary_one_past_its_limits_is_rejected(self):
        filler = SUMMARY_MAX_BYTES + 1 - len(json.dumps({"large": ""}))
        nested = {"deep": json.loads("[" * 32 + "0" + "]" * 32)}
        cases = (({"large": "x" * filler}, "summary size limit"), (nested, "invalid JSON"))
        for value, reason in (*cases, ({"nodes": [0] * 4095}, "invalid JSON")):
            with self.subTest(reason=reason):
                (self.produced / "boundary.json").write_text(json.dumps(value), encoding="utf-8")
                self.rejected(reason)

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
                self.rejected("unsafe artifact filename")
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
        self.rejected("unsafe artifact filename")

    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_junction_is_rejected(self):
        import _winapi

        outside = self.root / "outside"
        outside.mkdir()
        (outside / "canary").write_bytes(self.marker)
        _winapi.CreateJunction(str(outside), str(self.produced / "junction"))
        self.rejected(LINKED)

    @POSIX_ONLY
    def test_search_only_work_folder_gives_the_same_outcome_in_both_walks(self):
        """Review round 5 (A2, I2): the container owns /work and can drop its read bit;
        the descriptor walk needed read permission only to look up results/."""
        (self.produced / "table.csv").write_bytes(b"ordinary output\n")
        self.work.chmod(0o100)
        self.addCleanup(self.work.chmod, 0o700)
        self.assertEqual(self.collect()["status"], "collected")

    def test_binary_bytes_are_copied_exactly(self):
        payload = b"line\r\nnext\n\x1a\x00tail"
        (self.produced / "binary.bin").write_bytes(payload)
        result = self.collect()
        self.assertEqual((self.destination / "binary.bin").read_bytes(), payload)
        self.assertEqual(result["files"][0]["sha256"], hashlib.sha256(payload).hexdigest())


@unittest.skipUnless(DESCRIPTOR_APIS, "POSIX descriptor walk")
class DescriptorCollectionTests(CollectionCases, unittest.TestCase):
    method = "descriptor"

    def test_source_path_past_the_path_length_limit_is_checked_without_a_crash(self):
        """Review round 5 (A1): the test mode read the source by path and crashed on
        a tree the descriptor walk had collected; the path walk cannot open it (I2)."""
        work = self.root / ("w" * 200) / ("x" * 200) / "work"
        (work / "results").mkdir(parents=True)
        current = os.open(work / "results", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for level in range(16):  # 16 x 244 characters: past Linux's 4,096
                name = f"d{level:02d}" + "a" * 240
                os.mkdir(name, dir_fd=current)
                inner = os.open(name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=current)
                os.close(current)
                current = inner
            fd = os.open("f.txt", os.O_WRONLY | os.O_CREAT, 0o644, dir_fd=current)
            os.write(fd, b"deep")
            os.close(fd)
        finally:
            os.close(current)
        result = collect_results(work, self.destination, method="descriptor")
        self.assertEqual(result["status"], "collected")
        self.assertEqual([row["bytes"] for row in result["files"]], [4])

    def test_work_path_just_under_the_path_limit_is_checked_without_a_crash(self):
        """Review round 6 (A1): work fits the path limit but work/results does not; the
        test mode read the results folder by path and crashed, then reported a false I2."""
        limit = os.pathconf(self.root, "PC_PATH_MAX") - 1
        work = str(self.root)
        while len(work) < limit - 4 - 201:
            work = os.path.join(work, "d" * 200)
        work = os.path.join(work, "w" * (limit - 4 - len(work) - 1))  # 5 under the limit
        os.makedirs(work)
        folder = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.mkdir("results", dir_fd=folder)
            results = os.open("results", os.O_RDONLY | os.O_DIRECTORY, dir_fd=folder)
            output = os.open("table.csv", os.O_WRONLY | os.O_CREAT, 0o644, dir_fd=results)
            os.write(output, b"ordinary\n")
            os.close(output)
            os.close(results)
        finally:
            os.close(folder)
        result = collect_results(work, self.destination, method="descriptor")
        self.assertEqual(result["status"], "collected")


@POSIX_ONLY
class SourceChainCheckTests(unittest.TestCase):
    """Review round 6 (A2): a link in a recorded file's source chain must fail the test
    mode's Q1 check by name, not as an OSError from opening through the link."""

    def check(self, relative, place_link, descriptors):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "work/results"
            results.mkdir(parents=True)
            (root / "outside").mkdir()
            (root / "outside/f").write_bytes(b"x")
            place_link(results, root / "outside")
            # The snapshot a broken collector would have made by following the link.
            destination = root / "destination"
            (destination / relative).parent.mkdir(parents=True, exist_ok=True)
            (destination / relative).write_bytes(b"x")
            row = {"path": relative, "bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()}
            entries = relative.count("/") + 1
            report = {"files": [row], "entries": entries, "bytes": 1, "summaries": {}}
            with patch("output_collection.DESCRIPTOR_APIS", descriptors):
                with self.assertRaisesRegex(ContractViolation, "^Q1: " + relative + "$"):
                    check_collected(root / "work", destination, report, DEFAULT_LIMITS, "path")

    def test_linked_folder_and_linked_file_fail_q1_in_both_ways_of_reading(self):
        def folder_link(results, outside):
            (results / "sub").symlink_to(outside, target_is_directory=True)

        def file_link(results, outside):
            (results / "f").symlink_to(outside / "f")

        for descriptors in (DESCRIPTOR_APIS, False):
            for relative, place in (("sub/f", folder_link), ("f", file_link)):
                with self.subTest(relative=relative, descriptors=descriptors):
                    self.check(relative, place, descriptors)


class RoundSevenCheckTests(unittest.TestCase):
    """Review round 7: the test-mode checks and the path walk."""

    def test_a_recorded_file_missing_from_the_source_fails_q1_by_name(self):
        """A missing file, folder or results folder surfaced as FileNotFoundError."""
        cases = (("missing file", "f", True), ("missing folder", "sub/f", True))
        cases += (("missing results", "f", False),)
        for label, relative, make_results in cases:
            for descriptors in sorted({DESCRIPTOR_APIS, False}):
                with self.subTest(case=label, descriptors=descriptors):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root / "work").mkdir()
                        if make_results:
                            (root / "work/results").mkdir()
                        destination = root / "destination"
                        (destination / relative).parent.mkdir(parents=True, exist_ok=True)
                        (destination / relative).write_bytes(b"x")
                        row = {"path": relative, "bytes": 1}
                        row["sha256"] = hashlib.sha256(b"x").hexdigest()
                        entries = relative.count("/") + 1
                        report = {"files": [row], "entries": entries, "bytes": 1, "summaries": {}}
                        with patch("output_collection.DESCRIPTOR_APIS", descriptors):
                            with self.assertRaisesRegex(ContractViolation, "^Q1: "):
                                check_collected(
                                    root / "work", destination, report, DEFAULT_LIMITS, "path"
                                )

    @NEEDS_CHECKS
    @unittest.skipUnless(os.name == "posix" and DESCRIPTOR_APIS, "PATH_MAX and descriptor walk")
    def test_a_long_temporary_folder_never_silences_an_i2_disagreement(self):
        """The reference walk's own snapshot path in a long TMPDIR failed with
        ENAMETOOLONG, which passed for a long path in the tree and skipped I2."""
        import output_collection

        real = output_collection.other_method_outcome

        def disagreeing(work, limits, method, *where):
            outcome = real(work, limits, method, *where)
            if outcome[0] != "collected":
                return outcome
            return ("collected", [{"path": "x", "bytes": 0, "sha256": ""}], 1, 0, {})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Short enough to hold the reference snapshot's own folders, too short to
            # hold the tree's 200-character folder below them (PATH_MAX 4096).
            long_tmp = root / "t"
            while len(str(long_tmp)) < 4096 - 250:
                long_tmp = long_tmp / ("t" * 200)
            os.makedirs(long_tmp)
            results = root / "w/work/results" / ("d" * 200)
            results.mkdir(parents=True)
            (results / "f").write_text("f", encoding="utf-8")
            work = root / "w/work"
            with patch("output_collection.other_method_outcome", side_effect=disagreeing):
                for label, temporary in (("short", None), ("long", str(long_tmp))):
                    with self.subTest(tmpdir=label), patch.object(tempfile, "tempdir", temporary):
                        with self.assertRaises((ContractViolation, OSError)) as caught:
                            collect_results(
                                work, root / f"evidence-{label}/workload", method="descriptor"
                            )
                        if isinstance(caught.exception, ContractViolation):
                            self.assertTrue(str(caught.exception).startswith("I2"))

    @POSIX_ONLY
    def test_both_walks_read_the_folder_the_kernel_names_for_link_dot_dot(self):
        """os.path.abspath dropped 'link/..' as text, so the path walk read another
        folder than the descriptor walk for the same work path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for side, name in (("a", "lexical.txt"), ("elsewhere", "kernel.txt")):
                (root / side / "work/results").mkdir(parents=True)
                (root / side / "work/results" / name).write_text(name, encoding="utf-8")
            (root / "elsewhere/x").mkdir()
            (root / "a/link").symlink_to(root / "elsewhere/x", target_is_directory=True)
            work = os.path.join(root, "a", "link", "..", "work")
            for method in ("descriptor", "path"):
                with self.subTest(method=method):
                    collected = collect_results(work, root / f"ev-{method}/workload", method=method)
                    self.assertEqual([row["path"] for row in collected["files"]], ["kernel.txt"])


@POSIX_ONLY
class RoundEightCheckTests(unittest.TestCase):
    """Review round 8: the path walk's base and the I2 reference snapshot."""

    @NEEDS_CHECKS
    @unittest.skipUnless(DESCRIPTOR_APIS, "descriptor walk")
    def test_the_i2_check_compares_with_the_path_walk(self):
        """Mutation testing (round 8): no test showed that the I2 check walks the tree the
        other way; a reference made by the same walk agrees with any fault of that walk."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work/results").mkdir(parents=True)
            (root / "work/results/table.csv").write_text("a\n", encoding="utf-8")
            refused = RejectedOutput("path walk refused")
            with patch("output_collection.path_directory", side_effect=refused):
                with self.assertRaisesRegex(ContractViolation, "^I2: the two walks copied"):
                    collect_results(root / "work", root / "evidence/workload", method="descriptor")

    def test_an_absolute_work_path_needs_no_current_folder(self):
        """The path walk joined every path to os.getcwd(), which fails once the current
        folder is deleted, so it rejected a tree the descriptor walk collected (I2)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work/results/sub").mkdir(parents=True)
            (root / "work/results/sub/table.csv").write_text("a,b\n", encoding="utf-8")
            (root / "gone").mkdir()
            previous = os.getcwd()
            os.chdir(root / "gone")
            try:
                (root / "gone").rmdir()
                for method in ("descriptor", "path"):
                    with self.subTest(method=method):
                        collected = collect_results(
                            root / "work", root / f"ev-{method}/workload", method=method
                        )
                        self.assertEqual(
                            [row["path"] for row in collected["files"]], ["sub/table.csv"]
                        )
            finally:
                os.chdir(previous)

    @unittest.skipUnless(DESCRIPTOR_APIS, "descriptor walk")
    def test_the_reference_snapshot_fits_wherever_the_real_one_fits(self):
        """The I2 reference copy went to TMPDIR/tmpXXXXXXXX/snapshot. When that is longer
        than <output>/.collect-XXXXXXXX, a tree the real walk collected (or rejected)
        near PATH_MAX made the test mode raise ENAMETOOLONG instead."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "r"
            limit = os.pathconf(directory, "PC_PATH_MAX") - 1
            temporary = root / ("t" * 120)
            temporary.mkdir()
            for case in ("collected", "rejected"):
                with self.subTest(case=case), patch.object(tempfile, "tempdir", str(temporary)):
                    destination = output / case / "workload"
                    # The real snapshot (destination.parent/.collect-XXXXXXXX) just fits.
                    budget = limit - len(str(destination.parent / ".collect-xxxxxxxx")) - 1 - 4
                    results = root / case / "work/results"
                    results.mkdir(parents=True)
                    for name in ("a", "b"):
                        (results / name).mkdir()
                    first, second = [entry.name for entry in os.scandir(results)]
                    parts, length = [first], 2
                    while length + 201 < budget - 5:
                        parts.append("d" * 200)
                        length += 201
                    folder = results.joinpath(*parts)
                    folder.mkdir(parents=True, exist_ok=True)
                    descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        name = "f" * (budget - length)
                        fd = os.open(name, os.O_WRONLY | os.O_CREAT, 0o644, dir_fd=descriptor)
                        os.write(fd, b"x\n")
                        os.close(fd)
                    finally:
                        os.close(descriptor)
                    if case == "rejected":
                        os.mkfifo(results / second / "pipe")
                    if case == "collected":
                        report = collect_results(results.parent, destination, method="descriptor")
                        self.assertEqual(len(report["files"]), 1)
                    else:
                        with self.assertRaisesRegex(RejectedOutput, LINKED):
                            collect_results(results.parent, destination, method="descriptor")
                    self.assertEqual(
                        sorted(path.name for path in destination.parent.iterdir()),
                        ["workload"] if case == "collected" else [],
                    )


class RoundNineCheckTests(unittest.TestCase):
    """Review round 9: the snapshot folders' spelling and a full output volume."""

    @POSIX_ONLY
    def test_a_destination_reached_through_a_link_and_dotdot_collects(self):
        """Python 3.12+ mkdtemp returns abspath, which drops 'link/..' by text, so the
        snapshot named another folder than the one made: FileNotFoundError, no
        collection.json, and an empty .collect-* left beside the real destination."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work/results").mkdir(parents=True)
            (root / "work/results/table.csv").write_text("a\n", encoding="utf-8")
            (root / "real/deep").mkdir(parents=True)
            (root / "x").mkdir()
            (root / "x/link").symlink_to(root / "real/deep", target_is_directory=True)
            results = root / "x/link/../evidence"  # the kernel reads real/evidence
            for method in ("descriptor", "path"):
                with self.subTest(method=method):
                    target = results / method
                    report = collect_workload(root / "work", target, method=method)
                    self.assertEqual(report["status"], "collected")
                    self.assertEqual(
                        (root / "real/evidence" / method / "workload/table.csv").read_text(
                            encoding="utf-8"
                        ),
                        "a\n",
                    )
                    self.assertEqual(
                        sorted(path.name for path in (target).iterdir()),
                        ["collection.json", "workload"],
                    )
            self.assertEqual(list(root.rglob(".collect-*")), [])

    def reference_fails(self, error):
        """Let the real snapshot fill; fail every write into any later .collect-* folder."""
        first = []
        real_copy = output_collection.copy_opened

        def copy(fd, info, device, destination, limits, counts, same):
            folder = next(p for p in destination.parents if p.name.startswith(".collect-"))
            first[:] = first or [folder]
            if folder != first[0]:
                raise error(destination)
            return real_copy(fd, info, device, destination, limits, counts, same)

        return patch("output_collection.copy_opened", side_effect=copy)

    @NEEDS_CHECKS
    @unittest.skipUnless(DESCRIPTOR_APIS, "descriptor walk")
    def test_a_full_volume_under_the_reference_snapshot_is_no_i2_break(self):
        """A full volume fails a write with no file name, so the reference copy's own
        failure became the outcome 'rejected' and a false 'I2: the two walks copied
        different data'. It must surface as the OSError it is."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work/results").mkdir(parents=True)
            (root / "work/results/table.csv").write_text("a\n", encoding="utf-8")

            def full(destination):
                return OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

            with self.reference_fails(full):
                with self.assertRaises(OSError) as caught:
                    try:
                        collect_results(root / "work", root / "ev/workload", method="descriptor")
                    except ContractViolation as violation:
                        self.fail(f"false contract violation: {violation}")
            self.assertEqual(caught.exception.errno, errno.ENOSPC)
            self.assertEqual(sorted(path.name for path in (root / "ev").iterdir()), ["workload"])

    @NEEDS_CHECKS
    @unittest.skipUnless(DESCRIPTOR_APIS, "descriptor walk")
    def test_a_reference_error_is_recognised_in_a_relative_destination(self):
        """Python 3.11 mkdtemp(dir='.') returns './.collect-X', but copy_tree names its
        files '.collect-X/...' (pathlib drops './'), so an error there was no longer
        seen as the reference snapshot's own and became a false I2 report."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work/results").mkdir(parents=True)
            (root / "work/results/table.csv").write_text("a\n", encoding="utf-8")

            def unwritable(destination):
                return OSError(errno.EIO, os.strerror(errno.EIO), os.fspath(destination))

            previous = os.getcwd()
            os.chdir(root)
            try:
                with self.reference_fails(unwritable):
                    with self.assertRaises(OSError) as caught:
                        try:
                            collect_results(Path("work"), Path("workload"), method="descriptor")
                        except ContractViolation as violation:
                            self.fail(f"false contract violation: {violation}")
            finally:
                os.chdir(previous)
            self.assertEqual(caught.exception.errno, errno.EIO)
            self.assertEqual(list(root.glob(".collect-*")), [])

    def test_a_full_host_volume_is_named_as_such(self):
        """Review round 9 (cosmetic): a full host volume during collection was reported
        as "unreadable or changing output entry", which blames the audited output."""
        methods = ("descriptor", "path") if DESCRIPTOR_APIS else ("path",)
        for method in methods:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "work/results").mkdir(parents=True)
                (root / "work/results/table.csv").write_text("a\n", encoding="utf-8")
                full = OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
                with patch("output_collection.copy_opened", side_effect=full):
                    with contextlib.redirect_stdout(io.StringIO()):
                        report = collect_workload(root / "work", root / "ev", method=method)
                self.assertEqual(report["status"], "rejected")
                self.assertEqual(report["reason"], "host volume full during collection")
                self.assertEqual(
                    sorted(path.name for path in (root / "ev").iterdir()), ["collection.json"]
                )

    def test_each_refusal_and_report_field_is_exactly_as_documented(self):
        """Mutation testing (round 9): the tests matched these messages as substrings and
        never read the reports' "limits" field, so a changed message or key went
        unnoticed."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            (work / "results").mkdir(parents=True)
            (work / "results/table.csv").write_text("a\n", encoding="utf-8")
            (root / "taken").mkdir()
            refusals = {
                "unknown collection method": dict(method="other"),
                "collection limits must be positive": dict(limits=CollectionLimits(depth=0)),
                "collection destination must be outside the writable container mount": dict(
                    destination=work / "results/out"
                ),
                "collection destination already exists": dict(destination=root / "taken"),
            }
            for message, arguments in refusals.items():
                with self.subTest(message=message):
                    arguments = {"destination": root / "ev/workload", **arguments}
                    with self.assertRaises(ValueError) as caught:
                        collect_results(work, **arguments)
                    self.assertEqual(str(caught.exception), message)
            limits = CollectionLimits(entries=9)
            report = collect_results(work, root / "ev/workload", limits=limits)
            self.assertEqual(report["limits"], asdict(limits))
            broken = OSError(errno.EIO, os.strerror(errno.EIO))
            with patch("output_collection.copy_opened", side_effect=broken):
                with contextlib.redirect_stdout(io.StringIO()):
                    rejected = collect_workload(work, root / "ev2", limits=limits)
            self.assertEqual(rejected["reason"], "unreadable or changing output entry")
            self.assertEqual(rejected["limits"], asdict(limits))


@POSIX_ONLY
class RoundTenCheckTests(unittest.TestCase):
    """Review round 10: summary names looked up by path in a snapshot near PATH_MAX."""

    def test_a_snapshot_near_the_path_limit_without_summaries_collects(self):
        """The path walk looks up each summary name by its full path. In a snapshot whose
        path leaves room for the output's names but not for benchmark-summary.json, the
        lookup failed with ENAMETOOLONG: the path walk rejected the tree, and with the
        test mode on, the I2 reference raised that OSError for a collected tree."""
        with tempfile.TemporaryDirectory() as directory:
            limit = os.pathconf(directory, "PC_PATH_MAX") - 1
            work = Path(directory, "work")
            (work / "results").mkdir(parents=True)
            (work / "results/a").write_text("ordinary\n", encoding="utf-8")
            for method in ("descriptor", "path"):
                with self.subTest(method=method):
                    parent = os.path.join(directory, method)
                    # <parent>/.collect-XXXXXXXX/a fits; .../benchmark-summary.json does not.
                    target = limit - len("/.collect-xxxxxxxx/benchmark-summary.json") + 10
                    while len(parent) < target:
                        parent = os.path.join(parent, "d" * min(200, target - len(parent) - 1))
                    os.makedirs(parent)
                    report = collect_results(work, Path(parent, "workload"), method=method)
                    self.assertEqual(report["status"], "collected")
                    self.assertEqual(report["summaries"], {})
                    self.assertEqual(sorted(os.listdir(parent)), ["workload"])


class ExactReasonTests(unittest.TestCase):
    """Mutation testing (round 12): the rejection tests match a reason as a regex
    search, so a reason with text added around it still passed. collection.json shows
    the reason to a reader, so these three are compared exactly."""

    def test_rejection_reasons_are_reported_exactly(self):
        def symlink(results):
            try:
                os.symlink("elsewhere", results / "link")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"cannot create a symbolic link here: {exc}")

        cases = {
            "output file size limit exceeded": lambda results: (results / "large").write_bytes(
                b"x" * 5
            ),
            "linked, special or cross-device output entry": symlink,
            "summary size limit exceeded": lambda results: (results / "boundary.json").write_text(
                json.dumps({"large": "x" * SUMMARY_MAX_BYTES}), encoding="utf-8"
            ),
        }
        for reason, make in cases.items():
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                results = Path(directory, "work", "results")
                results.mkdir(parents=True)
                make(results)
                limits = CollectionLimits(file_bytes=4 if "file size" in reason else 2**20)
                with contextlib.redirect_stdout(io.StringIO()):
                    report = collect_workload(
                        Path(directory, "work"), Path(directory, "ev"), limits
                    )
                self.assertEqual(report["status"], "rejected")
                self.assertEqual(report["reason"], reason)


class RoundTwelveCheckTests(unittest.TestCase):
    @NEEDS_CHECKS
    def test_the_test_mode_reports_a_read_of_another_file(self):
        """Mutation testing (round 12): no test broke the I1 check before a read on
        purpose, so the check's message could be dropped or changed unnoticed. A ``same``
        that accepts any pair stands for an identity check that misses a swap."""
        with tempfile.TemporaryDirectory() as directory:
            checked, opened = Path(directory, "checked"), Path(directory, "opened")
            checked.write_bytes(b"checked\n")
            opened.write_bytes(b"opened\n")
            info = os.lstat(checked)
            fd = os.open(opened, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                with self.assertRaises(ContractViolation) as caught:
                    output_collection.read_opened(
                        fd, info, info.st_dev, 100, "changed", lambda chunk: None, lambda a, b: True
                    )
            finally:
                os.close(fd)
            self.assertEqual(
                str(caught.exception),
                "I1: about to read an entry that is not the one-link regular file checked by name",
            )


@POSIX_ONLY
class RoundThirteenCheckTests(unittest.TestCase):
    def test_a_destination_name_longer_than_the_snapshot_name_near_the_path_limit(self):
        """R13B-T1: the snapshot is written under its .collect-* name (17 characters) and
        then renamed. check_collected listed and read the destination by full path, so a
        tree that fit the path limit under the snapshot's name, renamed to a longer
        destination name, raised ENAMETOOLONG in the test mode instead of returning the
        report that the run returns with it off."""
        with tempfile.TemporaryDirectory() as directory:
            limit = os.pathconf(directory, "PC_PATH_MAX") - 1
            work, parent = Path(directory, "w"), Path(directory, "p")
            (work / "results").mkdir(parents=True)
            parent.mkdir()
            (work / "results/boundary.json").write_text('{"ok": true}', encoding="utf-8")
            # The deepest file's path under the snapshot is limit - 2 characters long.
            budget = limit - 2 - (len(str(parent)) + 1 + len(".collect-xxxxxxxx")) - 1
            parts, used = [], 0
            while budget - used > 210:
                parts.append("d" * 200)
                used += 201
            folder = Path(work, "results", *parts)
            folder.mkdir(parents=True)
            (folder / ("f" * (budget - used))).write_bytes(b"deep file\n")
            deepest = "/".join([*parts, "f" * (budget - used)])
            for method in ("descriptor", "path"):
                with self.subTest(method=method):
                    destination = parent / (method + "-evidence-" + "n" * 30)
                    self.assertGreater(len(str(destination)) + 1 + len(deepest), limit)
                    report = collect_results(work, destination, method=method)
                    self.assertEqual(report["status"], "collected")
                    self.assertIn(deepest, [row["path"] for row in report["files"]])
                    self.assertEqual(sorted(report["summaries"]), ["boundary.json"])

    def test_a_link_or_special_entry_in_the_snapshot_fails_q1_by_name(self):
        """Mutation testing of snapshot_walk: its lstat could follow links (both walks)
        or name the folder instead of the entry (path walk), and no test noticed,
        because no test put a link into a snapshot. A link to a file, a link to a
        folder and a FIFO in the snapshot must each fail Q1 with the link message."""

        def file_link(snapshot):
            (snapshot / "entry").symlink_to(snapshot / "f")

        def folder_link(snapshot):
            (snapshot / "folder").mkdir()
            (snapshot / "entry").symlink_to(snapshot / "folder", target_is_directory=True)

        def fifo(snapshot):
            os.mkfifo(snapshot / "entry")

        for name, place in (("file link", file_link), ("folder link", folder_link), ("fifo", fifo)):
            for descriptors in (DESCRIPTOR_APIS, False):
                with self.subTest(entry=name, descriptors=descriptors):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root / "work/results").mkdir(parents=True)
                        (root / "work/results/f").write_bytes(b"x")
                        snapshot = root / "destination"
                        snapshot.mkdir()
                        (snapshot / "f").write_bytes(b"x")
                        try:
                            place(snapshot)
                        except (AttributeError, NotImplementedError, OSError) as exc:
                            self.skipTest(f"cannot make a {name} here: {exc}")
                        digest = hashlib.sha256(b"x").hexdigest()
                        row = {"path": "f", "bytes": 1, "sha256": digest}
                        report = {"files": [row], "entries": 1, "bytes": 1, "summaries": {}}
                        with patch("output_collection.DESCRIPTOR_APIS", descriptors):
                            with self.assertRaisesRegex(
                                ContractViolation,
                                "^Q1: the snapshot holds a link or special entry$",
                            ):
                                check_collected(
                                    root / "work", snapshot, report, DEFAULT_LIMITS, "path"
                                )

    def test_the_test_mode_reports_each_broken_collection_rule(self):
        """Mutation testing (round 13): check_collected's Q1 and I2 checks could lose their
        condition, rule or message and no test noticed, because no test broke them one
        at a time. Each case breaks one rule on a real collection and expects that
        check's exact report."""

        def records(report, limits, work):
            report["files"].append({"path": "g", "bytes": 1, "sha256": "0" * 64})

        def rename_results(report, limits, work):
            (work / "results").rename(work / "gone")

        def hard_link(report, limits, work):
            os.link(work / "results/f", work / "f-link")

        def new_bytes(report, limits, work):
            (work / "results/f").write_bytes(b"y")

        def field(*keys, value):
            def change(report, limits, work):
                target = report
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value(target[keys[-1]])

            return change

        cases = {
            "^Q1: snapshot files differ from the records$": (records, DEFAULT_LIMITS),
            "^Q1: entry count differs$": (field("entries", value=lambda n: n + 1), None),
            "^Q1: entry limit exceeded$": (None, CollectionLimits(entries=0)),
            "^Q1$": (field("bytes", value=lambda n: n + 1), None),
            "^Q1: total byte limit exceeded$": (None, CollectionLimits(total_bytes=0)),
            "^Q1: f$": (field("files", 0, "sha256", value=lambda _: "0" * 64), None),
            "^Q1: no source results folder: f$": (rename_results, None),
            "^Q1: source bytes differ: f$": (new_bytes, None),
            "^I2: the two walks read summaries$": (
                field("summaries", value=lambda _: {"boundary.json": {}}),
                None,
            ),
        }
        cases_more = {
            "row bytes": (field("files", 0, "bytes", value=lambda n: n + 1), None),
            "file limit": (None, CollectionLimits(file_bytes=0)),
            "hard link": (hard_link, None),
        }
        for pattern, (change, limits) in [
            *cases.items(),
            *(("^Q1: f$", case) for case in cases_more.values()),
        ]:
            for method in ("descriptor", "path") if DESCRIPTOR_APIS else ("path",):
                if pattern.startswith("^I2") and method == "path":
                    continue
                with self.subTest(pattern=pattern, method=method, change=change):
                    with tempfile.TemporaryDirectory() as directory:
                        work = Path(directory, "work")
                        (work / "results").mkdir(parents=True)
                        (work / "results/f").write_bytes(b"x")
                        destination = Path(directory, "destination")
                        report = collect_results(work, destination, method=method)
                        self.assertEqual(report["status"], "collected")
                        check_collected(work, destination, report, DEFAULT_LIMITS, method)
                        limits = limits or DEFAULT_LIMITS
                        if change is not None:
                            try:
                                change(report, limits, work)
                            except OSError as exc:  # no hard links on this file system
                                self.skipTest(str(exc))
                        with self.assertRaisesRegex(ContractViolation, pattern):
                            check_collected(work, destination, report, limits, method)

    def test_the_test_mode_reports_a_source_file_on_another_device(self):
        """Mutation testing (round 13): the check that every part of a recorded file's
        source chain is on the results folder's device could lose its condition or rule
        unnoticed, since no test crosses a mount. The chain is shifted to another device
        number here, so the check must name the file."""
        import output_collection

        real = output_collection.source_chain

        def crossing(work, relative):
            chain, data = real(work, relative)
            last = chain[-1]
            moved = os.stat_result((*last[:2], last.st_dev + 1, *last[3:10]))
            return [*chain[:-1], moved], data

        for method in ("descriptor", "path") if DESCRIPTOR_APIS else ("path",):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as directory:
                work = Path(directory, "work")
                (work / "results").mkdir(parents=True)
                (work / "results/f").write_bytes(b"x")
                destination = Path(directory, "destination")
                report = collect_results(work, destination, method=method)
                with patch("output_collection.source_chain", crossing):
                    with self.assertRaisesRegex(ContractViolation, "^Q1: f$"):
                        check_collected(work, destination, report, DEFAULT_LIMITS, method)


@POSIX_ONLY
class RoundElevenCheckTests(unittest.TestCase):
    """Review round 11: a relative destination near PATH_MAX."""

    def test_a_relative_destination_near_the_path_limit_keeps_its_summaries(self):
        """R11B-1: copy_tree writes the snapshot by the destination's own spelling, but
        the path walk looks each summary up under the current folder. With a relative
        destination whose absolute spelling left no room for boundary.json, round 10's
        "absent" reading of ENAMETOOLONG dropped a summary that was in the snapshot (path
        walk), and with the test mode on the descriptor walk raised an I2 break."""
        start = os.getcwd()
        self.addCleanup(os.chdir, start)
        with tempfile.TemporaryDirectory() as directory:
            limit = os.pathconf(directory, "PC_PATH_MAX") - 1
            work = Path(directory, "work")
            (work / "results").mkdir(parents=True)
            (work / "results/boundary.json").write_text('{"no_capabilities": true}', "utf-8")
            (work / "results/a.txt").write_text("x\n", encoding="utf-8")
            # <cwd>/dest/.collect-XXXXXXXX fits the limit; .../boundary.json does not.
            target = limit - len("/dest/.collect-xxxxxxxx/boundary.json") + 5
            for method in ("descriptor", "path"):
                with self.subTest(method=method):
                    os.chdir(directory)
                    os.mkdir(method)
                    os.chdir(method)
                    while len(os.getcwd()) < target:
                        part = "c" * min(200, target - len(os.getcwd()) - 1)
                        os.mkdir(part)
                        os.chdir(part)
                    try:
                        report = collect_results(work, Path("dest/workload"), method=method)
                    except RejectedOutput:
                        self.assertEqual(method, "path")  # failing closed is allowed there
                        continue
                    finally:
                        held = os.listdir("dest/workload") if os.path.isdir("dest/workload") else []
                        os.chdir(start)
                    self.assertEqual(report["status"], "collected")
                    self.assertIn("boundary.json", held)
                    self.assertEqual(sorted(report["summaries"]), ["boundary.json"])


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
            self.rejected("output directory changed during collection")

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
            self.rejected(LINKED)
        self.assertTrue(swapped)

    @NEEDS_CHECKS
    def test_contract_check_catches_a_comparison_that_misses_a_different_file(self):
        """Review round 5 (B1): the I1 check repeated the type tests and never compared
        the opened file's identity with the checked name's."""
        (self.produced / "table.csv").write_bytes(b"ordinary output\n")
        blind = staticmethod(lambda info, opened: True)
        with patch.object(PathFolder, "same", blind):
            with self.stale_lstat(lambda info: {"st_ino": info.st_ino + 1}):
                with self.assertRaisesRegex(ContractViolation, "^I1"):
                    self.collect()

    def test_a_different_file_id_at_open_is_rejected(self):
        (self.produced / "table.csv").write_bytes(b"ordinary output\n")
        with self.stale_lstat(lambda info: {"st_ino": info.st_ino + 1}):
            self.rejected("output file changed during collection")


@POSIX_ONLY
class RoundFourteenCheckTests(unittest.TestCase):
    """Review round 14 (R14B-A1): the descriptor walk holds two descriptors per folder
    level and the path walk one. When the host's descriptor table ran out (EMFILE from
    the process limit, ENFILE from the system's) the directory open's error was wrapped
    as "missing, linked or unreadable output directory", and a listing's as "unreadable
    or changing output entry": a host limit blamed on the container output, as a full
    volume once was (round 9). In the test mode the path walk, which still fit, then
    collected the same tree, a false "I2: only the descriptor walk rejected"."""

    def test_an_exhausted_descriptor_table_is_named_as_the_hosts_limit(self):
        real_open, real_scandir = os.open, os.scandir
        for code in (errno.EMFILE, errno.ENFILE):
            # Each injection fires once, on the walk's first use of the results subfolder;
            # the snapshot cleanup and the test mode's reference walk run undisturbed.
            pending = []

            def opening(path, flags, *args, pending=pending, **kwargs):
                if pending and path == "sub" and kwargs.get("dir_fd") is not None:
                    raise OSError(pending.pop(), "exhausted")
                return real_open(path, flags, *args, **kwargs)

            def listing(target, pending=pending):
                if pending and isinstance(target, str) and target.endswith(os.sep + "sub"):
                    raise OSError(pending.pop(), "exhausted", target)
                return real_scandir(target)

            for method, name, failing in (
                ("descriptor", "open", opening),
                ("path", "scandir", listing),
            ):
                with self.subTest(method=method, errno=errno.errorcode[code]):
                    with tempfile.TemporaryDirectory() as directory:
                        work = Path(directory, "work")
                        (work / "results" / "sub").mkdir(parents=True)
                        (work / "results" / "sub" / "f").write_bytes(b"x")
                        pending.append(code)
                        with patch(f"output_collection.os.{name}", side_effect=failing):
                            report = collect_workload(
                                work, Path(directory, "results"), method=method
                            )
                    self.assertEqual(pending, [])
                    self.assertEqual(report["status"], "rejected")
                    self.assertEqual(
                        report["reason"], "host descriptor limit reached during collection"
                    )

    @NEEDS_CHECKS
    @unittest.skipUnless(DESCRIPTOR_APIS, "POSIX descriptor walk")
    def test_the_test_mode_runs_the_other_walk_after_a_rejection(self):
        """Mutation testing (round 14): no test showed that a rejection by the descriptor
        walk makes the test mode walk the same tree by path (I2). A planted rejection
        of the descriptor walk alone must be reported as an I2 break, and neither
        snapshot may be left behind."""
        real = output_collection.copy_tree

        def descriptor_only_rejection(work, snapshot, limits, method):
            if method == "descriptor":
                raise RejectedOutput("planted rejection of the descriptor walk")
            return real(work, snapshot, limits, method)

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory, "work")
            (work / "results").mkdir(parents=True)
            (work / "results" / "f").write_bytes(b"x")
            evidence = Path(directory, "evidence")
            with patch("output_collection.copy_tree", side_effect=descriptor_only_rejection):
                with self.assertRaisesRegex(ContractViolation, "^I2: only the descriptor walk"):
                    collect_results(work, evidence / "workload", method="descriptor")
            self.assertEqual(os.listdir(evidence), [])


def descriptor_limit_leaving(free):
    """A ``RLIMIT_NOFILE`` soft limit under which exactly ``free`` more descriptors can be
    opened. The limit bounds descriptor numbers, not their count: a gap below it, or a
    descriptor above it (a CI runner's own pipes), gives a process more room than the
    count suggests, so the limit is found from the numbers in use."""
    probe = os.open("/proc/self/fd", os.O_RDONLY)  # the lowest free number, reused below
    os.close(probe)
    taken = {int(name) for name in os.listdir("/proc/self/fd")} - {probe}
    limit = 0
    while limit - sum(1 for number in taken if number < limit) < free:
        limit += 1
    return limit


@POSIX_ONLY
class RoundFifteenCheckTests(unittest.TestCase):
    """Review round 15 (R15B-A1, R15B-A2): the cleanup after a rejection for an exhausted
    descriptor table, and a host fault at a directory open."""

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "needs /proc to count descriptors")
    def test_a_rejection_for_an_exhausted_table_leaves_no_snapshot(self):
        """shutil.rmtree holds a descriptor per folder level, so when the path walk ran
        out of descriptors at a file open, the cleanup ran out too: the OSError escaped
        collect_results (the rejection's own error only as its context), no
        collection.json was written and the partial snapshot stayed (Q2)."""
        import resource

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory, "work")
            folder = work.joinpath("results", *(["d"] * 8))
            folder.mkdir(parents=True)
            (folder / "f").write_bytes(b"x")
            evidence = Path(directory, "evidence")
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            # The walk lists nine folders (results and eight below) with a descriptor
            # each; the file open is then refused, and the cleanup needs one more.
            resource.setrlimit(resource.RLIMIT_NOFILE, (descriptor_limit_leaving(9), hard))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    report = collect_workload(work, evidence, method="path")
            finally:
                resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["reason"], "host descriptor limit reached during collection")
            self.assertEqual(os.listdir(evidence), ["collection.json"])

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "needs /proc to count descriptors")
    def test_the_snapshot_cleanup_removes_files_one_listing_at_a_time(self):
        """Mutation testing of the fix above: its tree held folders only, so the
        fallback's file removal ran on no file. When shutil.rmtree, which holds a
        descriptor per folder level, meets the exhausted table, remove_snapshot takes
        the private snapshot apart bottom-up, files and folders, with one listing open."""
        import resource

        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory, ".collect-test")
            folder = snapshot
            for level in range(8):
                folder.mkdir(mode=0o700)
                (folder / f"f{level}").write_bytes(b"x")
                folder = folder / "d"
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(resource.RLIMIT_NOFILE, (descriptor_limit_leaving(4), hard))
            try:
                with self.assertRaises(OSError) as raised:
                    shutil.rmtree(snapshot)
                self.assertEqual(raised.exception.errno, errno.EMFILE)
                output_collection.remove_snapshot(snapshot)
            finally:
                resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
            self.assertFalse(snapshot.exists())

    @NEEDS_CHECKS
    @unittest.skipUnless(DESCRIPTOR_APIS, "POSIX descriptor walk")
    def test_a_host_fault_at_a_directory_open_is_no_i2_break(self):
        """directory_fd wrapped every error but an exhausted table as "missing, linked or
        unreadable output directory", so a transient host fault at a folder open (ENOMEM,
        EIO) made the test mode walk the tree again by path, which collected it: a false
        "I2: only the descriptor walk rejected". Such an error is the host's: it is
        reported as one at any other call of the walk, and the I2 reference is skipped."""
        real_open = os.open
        for code in (errno.ENOMEM, errno.EIO):
            pending = [code]

            def opening(path, flags, *args, pending=pending, **kwargs):
                if pending and path == "sub" and kwargs.get("dir_fd") is not None:
                    raise OSError(pending.pop(), "host fault")
                return real_open(path, flags, *args, **kwargs)

            with self.subTest(errno=errno.errorcode[code]):
                with tempfile.TemporaryDirectory() as directory:
                    work = Path(directory, "work")
                    (work / "results" / "sub").mkdir(parents=True)
                    (work / "results" / "sub" / "f").write_bytes(b"x")
                    evidence = Path(directory, "evidence")
                    with patch("output_collection.os.open", side_effect=opening):
                        with contextlib.redirect_stdout(io.StringIO()):
                            report = collect_workload(work, evidence, method="descriptor")
                    self.assertEqual(pending, [])
                    self.assertEqual(report["status"], "rejected")
                    self.assertEqual(report["reason"], "unreadable or changing output entry")
                    self.assertEqual(os.listdir(evidence), ["collection.json"])


if __name__ == "__main__":
    unittest.main()
