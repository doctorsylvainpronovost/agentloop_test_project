import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/weather"


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", DEFAULT_DATABASE_URL)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_alembic_sql(*args: str) -> str:
    result = run_alembic(*args, "--sql")
    assert result.returncode == 0, result.stderr
    return result.stdout


def _database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


@pytest.fixture(scope="module")
def postgres_engine():
    engine = create_engine(_database_url())
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except DBAPIError as exc:
        pytest.skip(f"PostgreSQL is not available for migration integration tests: {exc}")
    yield engine
    engine.dispose()


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


def test_upgrade_sql_contains_users_and_saved_locations_contracts() -> None:
    upgrade_sql = run_alembic_sql("upgrade", "head")

    assert "CREATE TABLE users" in upgrade_sql
    assert "CREATE TABLE saved_locations" in upgrade_sql
    assert "CONSTRAINT fk_saved_locations_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)" in upgrade_sql
    assert "CONSTRAINT ck_saved_locations_latitude_range CHECK (latitude >= -90 AND latitude <= 90)" in upgrade_sql
    assert "CONSTRAINT ck_saved_locations_longitude_range CHECK (longitude >= -180 AND longitude <= 180)" in upgrade_sql
    assert "latitude NUMERIC(9, 6) NOT NULL" in upgrade_sql
    assert "longitude NUMERIC(9, 6) NOT NULL" in upgrade_sql
    assert "CREATE INDEX ix_saved_locations_user_id ON saved_locations (user_id)" in upgrade_sql
    assert "CREATE INDEX ix_saved_locations_user_id_name ON saved_locations (user_id, name)" in upgrade_sql


def test_downgrade_sql_drops_indexes_before_tables() -> None:
    downgrade_sql = run_alembic_sql("downgrade", "heads:base")

    drop_compound_index = downgrade_sql.find("DROP INDEX ix_saved_locations_user_id_name;")
    drop_single_index = downgrade_sql.find("DROP INDEX ix_saved_locations_user_id;")
    drop_saved_locations = downgrade_sql.find("DROP TABLE saved_locations;")
    drop_users = downgrade_sql.find("DROP TABLE users;")

    assert -1 not in (drop_compound_index, drop_single_index, drop_saved_locations, drop_users)
    assert drop_compound_index < drop_single_index < drop_saved_locations < drop_users


def test_upgrade_and_downgrade_round_trip_with_constraint_enforcement(postgres_engine) -> None:
    downgrade = run_alembic("downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr

    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    schema = inspect(postgres_engine)
    assert set(("users", "saved_locations")).issubset(set(schema.get_table_names()))

    users_columns = {column["name"]: column for column in schema.get_columns("users")}
    saved_columns = {column["name"]: column for column in schema.get_columns("saved_locations")}

    for name in ("id", "email", "created_at"):
        assert users_columns[name]["nullable"] is False

    for name in ("id", "user_id", "name", "latitude", "longitude", "created_at"):
        assert saved_columns[name]["nullable"] is False

    assert schema.get_pk_constraint("users")["constrained_columns"] == ["id"]
    assert schema.get_pk_constraint("saved_locations")["constrained_columns"] == ["id"]

    foreign_keys = schema.get_foreign_keys("saved_locations")
    assert any(
        fk["name"] == "fk_saved_locations_user_id_users"
        and fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and fk["referred_columns"] == ["id"]
        for fk in foreign_keys
    )

    latitude_type = saved_columns["latitude"]["type"]
    longitude_type = saved_columns["longitude"]["type"]
    assert getattr(latitude_type, "precision", None) == 9
    assert getattr(latitude_type, "scale", None) == 6
    assert getattr(longitude_type, "precision", None) == 9
    assert getattr(longitude_type, "scale", None) == 6

    check_constraints = {constraint["name"]: constraint.get("sqltext", "") for constraint in schema.get_check_constraints("saved_locations")}
    assert "ck_saved_locations_latitude_range" in check_constraints
    assert "ck_saved_locations_longitude_range" in check_constraints
    assert "latitude >= -90" in check_constraints["ck_saved_locations_latitude_range"]
    assert "latitude <= 90" in check_constraints["ck_saved_locations_latitude_range"]
    assert "longitude >= -180" in check_constraints["ck_saved_locations_longitude_range"]
    assert "longitude <= 180" in check_constraints["ck_saved_locations_longitude_range"]

    indexes = {index["name"]: index["column_names"] for index in schema.get_indexes("saved_locations")}
    assert indexes["ix_saved_locations_user_id"] == ["user_id"]
    assert indexes["ix_saved_locations_user_id_name"] == ["user_id", "name"]

    with postgres_engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, email, created_at) VALUES (1001, 'integration@example.com', NOW())"))
        connection.execute(
            text(
                "INSERT INTO saved_locations (id, user_id, name, latitude, longitude, created_at) "
                "VALUES (2001, 1001, 'Downtown', 45.123456, -122.123456, NOW())"
            )
        )

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO saved_locations (id, user_id, name, latitude, longitude, created_at) "
                    "VALUES (2002, 1001, 'OutOfBoundsLat', 91.000000, 20.000000, NOW())"
                )
            )

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO saved_locations (id, user_id, name, latitude, longitude, created_at) "
                    "VALUES (2003, 1001, 'OutOfBoundsLon', 30.000000, 181.000000, NOW())"
                )
            )

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO saved_locations (id, user_id, name, latitude, longitude, created_at) "
                    "VALUES (2004, 9999, 'Orphan', 20.000000, 10.000000, NOW())"
                )
            )

    downgrade = run_alembic("downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr

    after_downgrade = inspect(postgres_engine)
    remaining_tables = set(after_downgrade.get_table_names())
    assert "users" not in remaining_tables
    assert "saved_locations" not in remaining_tables
