import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def test_python3_runtime_is_available() -> None:
    assert sys.version_info.major >= 3


def test_required_packages_are_importable() -> None:
    import alembic  # noqa: F401
    import psycopg  # noqa: F401
    import sqlalchemy  # noqa: F401


def test_requirements_include_migration_dependencies() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "alembic" in requirements
    assert "sqlalchemy" in requirements
    assert "psycopg[binary]" in requirements
    assert "pytest" in requirements


def test_database_url_is_postgresql() -> None:
    from app.config import get_database_url, is_postgresql_url

    db_url = get_database_url()
    assert is_postgresql_url(db_url)


def test_alembic_uses_application_database_url() -> None:
    from alembic.config import Config
    from app.config import get_database_url

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    assert cfg.get_main_option("sqlalchemy.url") == get_database_url()


def test_single_head_and_baseline_revision_discoverable() -> None:
    heads = run_alembic("heads")
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.count("(head)") == 1
    assert "0001_baseline" in heads.stdout


def test_migration_commands_history_and_upgrade_sql() -> None:
    history = run_alembic("history")
    assert history.returncode == 0, history.stderr
    assert "0001_baseline" in history.stdout

    upgrade_sql = run_alembic("upgrade", "head", "--sql")
    assert upgrade_sql.returncode == 0, upgrade_sql.stderr
    assert "0001_baseline" in upgrade_sql.stdout

    repeat_upgrade_sql = run_alembic("upgrade", "head", "--sql")
    assert repeat_upgrade_sql.returncode == 0, repeat_upgrade_sql.stderr


def test_baseline_sql_includes_cache_constraints_and_lookup_index() -> None:
    upgrade_sql = run_alembic("upgrade", "head", "--sql")
    assert upgrade_sql.returncode == 0, upgrade_sql.stderr

    sql_text = upgrade_sql.stdout
    assert "CREATE TABLE users" in sql_text
    assert "CREATE TABLE saved_locations" in sql_text
    assert "CREATE TABLE weather_cache" in sql_text
    assert "CONSTRAINT uq_weather_cache_version UNIQUE (location_name, units, forecast_date, fetched_at)" in sql_text
    assert "CREATE INDEX ix_weather_cache_lookup" in sql_text
    assert "expires_at TIMESTAMP WITH TIME ZONE NOT NULL" in sql_text


def test_readme_documents_cache_ttl_and_lookup_query() -> None:
    readme = (ROOT / "alembic" / "README").read_text(encoding="utf-8")

    assert "`users`" in readme
    assert "`saved_locations`" in readme
    assert "`weather_cache`" in readme
    assert "expires_at <= NOW()" in readme
    assert "ORDER BY fetched_at DESC LIMIT 1" in readme
