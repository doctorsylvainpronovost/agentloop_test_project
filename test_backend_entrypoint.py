import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from backend.main import MESSAGE, main


class TestBackendEntrypoint(unittest.TestCase):
    def test_main_returns_zero_and_prints_message(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main()

        self.assertEqual(code, 0)
        self.assertEqual(buffer.getvalue(), f"{MESSAGE}\n")

    def test_entry_script_runs_successfully(self) -> None:
        script_path = Path(__file__).resolve().parent / "backend" / "main.py"
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, f"{MESSAGE}\n")
        self.assertEqual(completed.stderr, "")

    def test_entry_script_is_directly_executable(self) -> None:
        script_path = Path(__file__).resolve().parent / "backend" / "main.py"
        completed = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, f"{MESSAGE}\n")
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
