import os
import re
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


def test_weather_cache_upgrade_sql_contains_constraints_indexes_and_comments() -> None:
    upgrade_sql = run_alembic("upgrade", "head", "--sql")
    assert upgrade_sql.returncode == 0, upgrade_sql.stderr

    sql = upgrade_sql.stdout

    assert "CREATE TABLE weather_cache" in sql
    assert "payload JSONB NOT NULL" in sql
    assert "expires_at TIMESTAMP WITH TIME ZONE NOT NULL" in sql
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL" in sql
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL" in sql

    assert "CONSTRAINT ck_weather_cache_units_valid CHECK (units IN ('metric', 'imperial'))" in sql
    assert "CONSTRAINT ck_weather_cache_range_valid CHECK (range IN ('1d', '3d', '7d'))" in sql
    assert "CONSTRAINT uq_weather_cache_key_version UNIQUE (lat, lon, units, range, created_at)" in sql

    index_pattern = re.compile(
        r"CREATE INDEX ix_weather_cache_lookup_latest\s+ON weather_cache "
        r"\(lat, lon, units, range, created_at DESC, expires_at DESC\)",
        re.IGNORECASE | re.MULTILINE,
    )
    assert index_pattern.search(sql), sql

    assert "COMMENT ON TABLE weather_cache IS" in sql
    assert "COMMENT ON CONSTRAINT uq_weather_cache_key_version ON weather_cache IS" in sql
    assert "COMMENT ON INDEX ix_weather_cache_lookup_latest IS" in sql


def test_weather_cache_downgrade_sql_removes_index_and_table() -> None:
    downgrade_sql = run_alembic("downgrade", "0001_baseline:base", "--sql")
    assert downgrade_sql.returncode == 0, downgrade_sql.stderr

    sql = downgrade_sql.stdout
    assert "DROP INDEX IF EXISTS ix_weather_cache_lookup_latest" in sql
    assert "DROP TABLE weather_cache" in sql
