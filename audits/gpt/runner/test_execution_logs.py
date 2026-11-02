import os
import signal
import sys
import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
