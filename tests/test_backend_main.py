import subprocess
import sys
from pathlib import Path
import unittest


class BackendMainTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
