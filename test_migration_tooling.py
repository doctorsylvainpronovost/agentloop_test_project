import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/weather")
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_root_level_pytest_discovery_for_migration_stack() -> None:
    assert (ROOT / "alembic.ini").exists()
    assert (ROOT / "alembic" / "versions" / "0001_baseline.py").exists()


def test_root_level_pytest_discovery_for_postgresql_settings() -> None:
    from app.config import get_database_url, is_postgresql_url

    assert is_postgresql_url(get_database_url())


def test_root_level_pytest_discovery_for_alembic_heads() -> None:
    heads = run_alembic("heads")
    assert heads.returncode == 0, heads.stderr
    assert "0001_baseline" in heads.stdout
