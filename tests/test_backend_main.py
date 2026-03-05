import subprocess
import sys
from pathlib import Path

def test_backend_main_runs_successfully() -> None:
    script_path = Path(__file__).resolve().parents[1] / "backend" / "main.py"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Backend scaffold is running." in result.stdout
    assert result.stderr == ""
