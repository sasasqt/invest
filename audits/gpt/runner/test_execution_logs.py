import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("CONTRACT_CHECKS", "1")

from isolated_runner import run_bounded

# The child starts a grandchild that inherits its stdout and outlives it.
HOLDER = (
    "import subprocess, sys;"
    "sleeper = [sys.executable, '-c', 'import time; time.sleep(60)'];"
    "p = subprocess.Popen(sleeper, stdout=sys.stdout);"
    "print(p.pid, flush=True)"
)


class ExecutionLogTests(unittest.TestCase):
    def test_normal_output_and_status_are_retained(self):
        result, reason = run_bounded(
            [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'ordinary\\n');sys.exit(7)"]
        )
        self.assertEqual((result.returncode, reason), (7, None))
        self.assertEqual(result.stdout, "ordinary\n")

    def test_environment_is_passed_and_stderr_is_kept(self):
        script = (
            "import os,sys;print(os.environ['AUDIT_MARK'],flush=True);sys.stderr.write('to err')"
        )
        argv = [sys.executable, "-c", script]
        result, reason = run_bounded(argv, env=dict(os.environ, AUDIT_MARK="from-env"))
        self.assertEqual((result.returncode, reason), (0, None))
        self.assertEqual(result.stdout.split(), ["from-env", "to", "err"])
        self.assertEqual((result.args, result.stderr), (argv, ""))

    def test_log_crossing_the_limit_keeps_exactly_the_limit(self):
        script = (
            "import sys, time; o = sys.stdout.buffer;"
            "o.write(b'a' * 600); o.flush(); time.sleep(0.3); o.write(b'b' * 1000); o.flush()"
        )
        result, reason = run_bounded([sys.executable, "-c", script], max_log_bytes=1024)
        self.assertEqual((result.returncode, reason), (125, "log_limit"))
        self.assertEqual(result.stdout, "a" * 600 + "b" * 424)

    def test_smallest_log_limit_is_accepted(self):
        result, reason = run_bounded([sys.executable, "-c", "pass"], max_log_bytes=1)
        self.assertEqual((result.returncode, reason), (0, None))

    def test_invalid_utf8_output_is_kept_as_replacement_characters(self):
        script = "import sys;sys.stdout.buffer.write(b'ok \\xff\\xfe end')"
        result, reason = run_bounded([sys.executable, "-c", script])
        self.assertEqual((result.returncode, reason), (0, None))
        self.assertEqual(result.stdout, "ok \ufffd\ufffd end")

    def test_pipe_is_closed_once_the_reader_is_done(self):
        made, real = [], subprocess.Popen

        def popen(*args, **kwargs):
            made.append(real(*args, **kwargs))
            return made[-1]

        with patch("isolated_runner.subprocess.Popen", side_effect=popen):
            run_bounded([sys.executable, "-c", "print('x')"])
        for thread in threading.enumerate():
            if thread.name == "run_bounded-reader":
                thread.join(5)
        self.assertTrue(made[0].stdout.closed)

    def test_large_stdout_is_bounded_and_fails(self):
        result, reason = run_bounded(
            [sys.executable, "-c", "import sys;sys.stdout.write('x'*100000)"], max_log_bytes=1024
        )
        self.assertEqual((result.returncode, reason), (125, "log_limit"))
        self.assertEqual(len(result.stdout), 1024)

    def test_timeout_is_retained_as_failure(self):
        result, reason = run_bounded(
            [sys.executable, "-c", "import time;print('started',flush=True);time.sleep(10)"],
            timeout=0.2,
        )
        self.assertEqual((result.returncode, reason), (124, "timeout"))
        self.assertIn("started", result.stdout)

    def test_grandchild_holding_the_pipe_cannot_hang_the_host(self):
        started = time.monotonic()
        result, reason = run_bounded([sys.executable, "-c", HOLDER], timeout=2)
        elapsed = time.monotonic() - started
        os.kill(int(result.stdout.split()[0]), signal.SIGTERM)
        self.assertEqual((result.returncode, reason), (124, "timeout"))
        self.assertLess(elapsed, 20)

    def test_output_split_across_reads_is_kept_whole(self):
        script = "import sys,time\nfor n in range(50):\n    print(n, flush=True); time.sleep(0.002)"
        result, reason = run_bounded([sys.executable, "-c", script])
        self.assertEqual((result.returncode, reason), (0, None))
        self.assertEqual(result.stdout.split(), [str(n) for n in range(50)])

    def test_output_past_an_exactly_full_log_is_a_log_limit(self):
        script = (
            "import sys, time; o = sys.stdout.buffer;"
            "o.write(b'x' * 1024); o.flush(); time.sleep(0.3); o.write(b'y')"
        )
        result, reason = run_bounded([sys.executable, "-c", script], max_log_bytes=1024)
        self.assertEqual((result.returncode, reason), (125, "log_limit"))
        self.assertEqual(result.stdout, "x" * 1024)

    def test_output_exactly_at_the_limit_is_kept(self):
        result, reason = run_bounded(
            [sys.executable, "-c", "import sys;sys.stdout.write('x'*1024)"], max_log_bytes=1024
        )
        self.assertEqual((result.returncode, reason), (0, None))
        self.assertEqual(len(result.stdout), 1024)

    def test_child_that_closed_its_output_is_waited_for_without_spinning(self):
        script = "import os, time; os.close(1); os.close(2); time.sleep(1.5)"
        before = time.process_time()
        result, reason = run_bounded([sys.executable, "-c", script], timeout=30)
        spent = time.process_time() - before
        self.assertEqual((result.returncode, reason), (0, None))
        self.assertLess(spent, 0.5, "the host spun while the child still ran")

    def test_reader_failure_ends_the_wait_at_once(self):
        """Nothing drains the pipe after the reader failed, so waiting cannot help."""
        real = subprocess.Popen

        class FailsOnSecondRead:
            def __init__(self, inner):
                self.inner, self.reads = inner, 0

            def read1(self, size):
                self.reads += 1
                if self.reads > 1:
                    raise OSError("pipe broke")
                return self.inner.read1(size)

            def close(self):
                self.inner.close()

        def popen(*args, **kwargs):
            process = real(*args, **kwargs)
            process.stdout = FailsOnSecondRead(process.stdout)
            return process

        writer = "import sys\nwhile True: sys.stdout.write('x' * 4096); sys.stdout.flush()"
        started = time.monotonic()
        with patch("isolated_runner.subprocess.Popen", side_effect=popen):
            with self.assertRaisesRegex(RuntimeError, "^container log reader failed$"):
                run_bounded([sys.executable, "-c", writer], timeout=20)
        self.assertLess(time.monotonic() - started, 5)

    def test_child_that_closed_its_output_still_meets_the_deadline(self):
        """Mutation testing: waiting for a child without output must keep the deadline."""
        script = "import os, time; os.close(1); os.close(2); time.sleep(30)"
        started = time.monotonic()
        result, reason = run_bounded([sys.executable, "-c", script], timeout=1)
        self.assertEqual((result.returncode, reason), (124, "timeout"))
        self.assertLess(time.monotonic() - started, 15)

    def test_reader_blocked_by_a_grandchild_never_keeps_the_host_alive(self):
        """Mutation testing: the reader must be a daemon thread, or a grandchild holding
        the pipe keeps the host process from exiting after run_bounded returned."""
        host = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from isolated_runner import run_bounded;"
            f"result, _ = run_bounded([sys.executable, '-c', {HOLDER!r}], timeout=1);"
            "print(result.stdout.split()[0], flush=True)"
        )
        here = os.path.dirname(os.path.abspath(__file__))
        started = time.monotonic()
        done = subprocess.run(
            [sys.executable, "-c", host, here], capture_output=True, text=True, timeout=120
        )
        elapsed = time.monotonic() - started
        os.kill(int(done.stdout.split()[0]), signal.SIGTERM)
        self.assertLess(elapsed, 20, "the host process waited for the reader thread")

    def controlled_popen(
        self, *, after_start=None, before_first_read=None, first_read_delay=0, kill_log=None
    ):
        """Popen that runs ``after_start(process)`` before it returns, and whose log reader
        runs ``before_first_read(process)`` and then waits ``first_read_delay`` seconds
        before its first read; ``kill_log`` gets the times the child started and was killed."""
        real = subprocess.Popen

        class Controlled:
            def __init__(self, inner, process):
                self.inner, self.process, self.reads = inner, process, 0

            def read1(self, size):
                self.reads += 1
                if self.reads == 1:
                    if before_first_read:
                        before_first_read(self.process)
                    time.sleep(first_read_delay)
                return self.inner.read1(size)

            def close(self):
                self.inner.close()

        def popen(*args, **kwargs):
            process = real(*args, **kwargs)
            if kill_log is not None:
                kill_log["started"] = time.monotonic()
                kill = process.kill

                def recorded_kill():
                    kill_log.setdefault("killed", time.monotonic())
                    kill()

                process.kill = recorded_kill
            process.stdout = Controlled(process.stdout, process)
            if after_start:
                after_start(process)
            return process

        return patch("isolated_runner.subprocess.Popen", side_effect=popen)

    def test_a_log_limit_the_reader_reaches_after_the_child_exited_still_fails(self):
        """Review round 19 (R19A-T5): when the reader crosses the limit after the child
        has exited, the wait loop ends without seeing it; no test reached the check after
        the loop, so dropping it passed the suites and a cut log read as exit 0.
        ChatGPT's INV-PR42-O1: the reader now reads only once the child has exited, and
        the caller resumes only once the reader has stopped, so the wait loop never runs
        and the check after it is the only one that can see the limit."""
        script = "import sys; sys.stdout.write('x' * 2048)"

        class ReaderFirst(threading.Thread):
            def start(self):
                super().start()
                self.join(30)

        with (
            self.controlled_popen(before_first_read=lambda process: process.wait(30)),
            patch("isolated_runner.threading.Thread", ReaderFirst),
        ):
            result, reason = run_bounded([sys.executable, "-c", script], max_log_bytes=1024)
        self.assertEqual((result.returncode, reason), (125, "log_limit"))
        self.assertEqual(result.stdout, "x" * 1024)

    def test_a_timed_out_child_keeps_the_log_it_wrote_before_the_deadline(self):
        """Review round 19 (R19A-T5): no test had a reader still busy at the deadline, so
        returning without waiting for it passed the suites and dropped the last lines a
        timed-out container wrote, which are what a reader of execution.log needs.
        ChatGPT's INV-PR42-O1: the child is handed over only once it says its line is
        written (a marker file), so a slow child start cannot leave the log empty, and the
        reader reads 1.5 s after it starts, so it is always still busy at the deadline."""
        with tempfile.TemporaryDirectory() as folder:
            marker = os.path.join(folder, "written")
            script = (
                "import pathlib, sys, time; print('last words', flush=True); "
                f"pathlib.Path({marker!r}).touch(); time.sleep(30)"
            )

            def line_written(process):
                limit = time.monotonic() + 30
                while not os.path.exists(marker) and time.monotonic() < limit:
                    time.sleep(0.01)

            with self.controlled_popen(after_start=line_written, first_read_delay=1.5):
                result, reason = run_bounded([sys.executable, "-c", script], timeout=0.5)
        self.assertEqual((result.returncode, reason), (124, "timeout"))
        self.assertEqual(result.stdout.split(), ["last", "words"])

    def test_the_deadline_is_the_timeout_given(self):
        """Review round 19 (R19A-T5): the timeout tests allowed up to 15 s for a 1 s
        timeout, so a deadline twice as far passed the suites. ChatGPT's INV-PR42-O1:
        the bound is measured from the child's start to its kill, so the child's start,
        reaping and the reader's join do not count."""
        times = {}
        script = "import time; time.sleep(30)"
        started = time.monotonic()
        with self.controlled_popen(kill_log=times):
            result, reason = run_bounded([sys.executable, "-c", script], timeout=3)
        self.assertEqual((result.returncode, reason), (124, "timeout"))
        self.assertGreaterEqual(times["killed"] - started, 3)
        self.assertLess(times["killed"] - times["started"], 4.5)

    def test_limits_must_be_positive(self):
        for limits in ({"timeout": 0}, {"max_log_bytes": 0}):
            with self.assertRaisesRegex(ValueError, "^execution limits must be positive$"):
                run_bounded([sys.executable, "-c", "pass"], **limits)


if __name__ == "__main__":
    unittest.main()
