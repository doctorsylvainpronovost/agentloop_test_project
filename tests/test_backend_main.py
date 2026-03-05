import subprocess
import sys
import unittest
from pathlib import Path


class TestBackendMainScript(unittest.TestCase):
    def test_backend_main_runs_successfully(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "backend" / "main.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Backend scaffold is running.", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
