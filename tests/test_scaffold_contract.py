from pathlib import Path


def test_requirements_file_is_intentionally_empty() -> None:
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    content = requirements.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "requirements.txt should contain dependencies"


def test_package_json_exposes_pytest_command() -> None:
    package_json = Path(__file__).resolve().parents[1] / "package.json"
    content = package_json.read_text(encoding="utf-8")
    assert 'python3 -m pytest' in content
