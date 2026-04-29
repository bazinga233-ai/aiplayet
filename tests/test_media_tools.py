import sys
import unittest

from backend.media_tools import run_checked_command


class MediaToolsTests(unittest.TestCase):
    def test_run_checked_command_replaces_undecodable_subprocess_output(self) -> None:
        completed = run_checked_command(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes([0xA5]))",
            ],
            error_label="probe",
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "\ufffd")
