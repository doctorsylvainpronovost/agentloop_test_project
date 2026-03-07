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


def test_db_verification_script_includes_acceptance_criteria_test_filters() -> None:
    script = (ROOT / "scripts" / "verify_db_migration_and_cache_plan.sh").read_text(encoding="utf-8")

    assert "migration_repeatability_and_revision_integrity" in script
    assert "weather_cache_composite_uniqueness_and_versioning" in script
    assert "latest_non_expired_cache_retrieval_returns_highest_valid_version" in script
    assert "latest_non_expired_query_plan_prefers_weather_cache_index" in script
    assert "weather_cache_schema_documentation_is_present_and_accurate" in script
    assert "--junitxml" in script
    assert "Database verification requires executed integration tests" in script
