import subprocess
import sys
from pathlib import Path

from backend.main import MESSAGE, main


def test_main_returns_zero_and_prints_message(capsys) -> None:
    code = main()
    captured = capsys.readouterr()

    assert code == 0
    assert captured.out == f"{MESSAGE}\n"
    assert captured.err == ""


def test_entry_script_runs_successfully() -> None:
    script_path = Path(__file__).resolve().parent / "backend" / "main.py"
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == f"{MESSAGE}\n"
    assert completed.stderr == ""


def test_entry_script_is_directly_executable() -> None:
    script_path = Path(__file__).resolve().parent / "backend" / "main.py"
    completed = subprocess.run(
        [str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == f"{MESSAGE}\n"
    assert completed.stderr == ""
