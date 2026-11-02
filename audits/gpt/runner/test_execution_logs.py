import sys
import unittest

from isolated_runner import run_bounded


class ExecutionLogTests(unittest.TestCase):
    def test_normal_output_and_status_are_retained(self):
        result, reason = run_bounded(
            [sys.executable, "-c", "print('ordinary');raise SystemExit(7)"]
        )
        self.assertEqual((result.returncode, reason), (7, None))
        self.assertEqual(result.stdout, "ordinary\n")

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


if __name__ == "__main__":
    unittest.main()
