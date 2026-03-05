import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.weather_cache import fetch_latest_non_expired_weather_cache

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/weather"
LATEST_REVISION = "0001_baseline"
WEATHER_INDEX_NAME = "ix_weather_cache_lookup_latest_non_expired"
WEATHER_UNIQUE_NAME = "uq_weather_cache_lookup_cache_version"


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


def _current_revision(engine) -> Optional[str]:
    with engine.connect() as connection:
        version_table = connection.execute(text("SELECT to_regclass('public.alembic_version')::text")).scalar_one()
        if version_table is None:
            return None
        return connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()


def _normalized_plan(plan: str) -> str:
    return " ".join(plan.split())


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


def test_upgrade_sql_contains_schema_contracts() -> None:
    upgrade_sql = run_alembic_sql("upgrade", "head")

    assert "CREATE TABLE weather_cache" in upgrade_sql
    assert "cache_version INTEGER DEFAULT 1 NOT NULL" in upgrade_sql
    assert f"CONSTRAINT {WEATHER_UNIQUE_NAME} UNIQUE (latitude, longitude, units, forecast_range, cache_version)" in upgrade_sql
    assert "CONSTRAINT ck_weather_cache_cache_version_positive CHECK (cache_version >= 1)" in upgrade_sql
    assert f"CREATE INDEX {WEATHER_INDEX_NAME} ON weather_cache" in upgrade_sql
    assert "expires_at DESC" in upgrade_sql
    assert "cache_version DESC" in upgrade_sql
    assert "created_at DESC" in upgrade_sql
    assert "COMMENT ON TABLE weather_cache" in upgrade_sql
    assert "COMMENT ON COLUMN weather_cache.cache_version" in upgrade_sql
    assert "COMMENT ON INDEX ix_weather_cache_lookup_latest_non_expired" in upgrade_sql


def test_downgrade_sql_drops_weather_index_before_table() -> None:
    downgrade_sql = run_alembic_sql("downgrade", "heads:base")

    drop_weather_index = downgrade_sql.find("DROP INDEX ix_weather_cache_lookup_latest_non_expired;")
    drop_weather_cache = downgrade_sql.find("DROP TABLE weather_cache;")

    assert drop_weather_index > -1
    assert drop_weather_cache > -1
    assert drop_weather_index < drop_weather_cache


def test_migration_repeatability_and_revision_integrity(postgres_engine) -> None:
    down_to_base = run_alembic("downgrade", "base")
    assert down_to_base.returncode == 0, down_to_base.stderr
    assert _current_revision(postgres_engine) is None

    first_upgrade = run_alembic("upgrade", "head")
    assert first_upgrade.returncode == 0, first_upgrade.stderr
    assert _current_revision(postgres_engine) == LATEST_REVISION

    second_downgrade = run_alembic("downgrade", "base")
    assert second_downgrade.returncode == 0, second_downgrade.stderr
    assert _current_revision(postgres_engine) is None

    second_upgrade = run_alembic("upgrade", "head")
    assert second_upgrade.returncode == 0, second_upgrade.stderr
    assert _current_revision(postgres_engine) == LATEST_REVISION


def test_weather_cache_composite_uniqueness_and_versioning(postgres_engine) -> None:
    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    schema = inspect(postgres_engine)
    unique_constraints = {constraint["name"]: constraint["column_names"] for constraint in schema.get_unique_constraints("weather_cache")}
    assert unique_constraints[WEATHER_UNIQUE_NAME] == ["latitude", "longitude", "units", "forecast_range", "cache_version"]

    with postgres_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE weather_cache"))
        connection.execute(
            text(
                "INSERT INTO weather_cache (id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at) "
                "VALUES (1, 45.500000, -122.600000, 'metric', 'week', 1, '{\"v\":1}', NOW(), NOW() + interval '30 minutes')"
            )
        )

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO weather_cache (id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at) "
                    "VALUES (2, 45.500000, -122.600000, 'metric', 'week', 1, '{\"dup\":true}', NOW(), NOW() + interval '30 minutes')"
                )
            )

    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO weather_cache (id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at) "
                "VALUES (3, 45.500000, -122.600000, 'metric', 'week', 2, '{\"v\":2}', NOW(), NOW() + interval '40 minutes')"
            )
        )
        rows = connection.execute(text("SELECT cache_version FROM weather_cache WHERE units = 'metric' ORDER BY cache_version")).scalars().all()

    assert rows == [1, 2]


def test_latest_non_expired_cache_retrieval_returns_highest_valid_version(postgres_engine) -> None:
    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    now = datetime.now(timezone.utc)
    with postgres_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE weather_cache"))
        connection.execute(
            text(
                "INSERT INTO weather_cache (id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at) "
                "VALUES (:id, :lat, :lon, :units, :forecast_range, :cache_version, :payload, :created_at, :expires_at)"
            ),
            [
                {
                    "id": 11,
                    "lat": "45.500000",
                    "lon": "-122.600000",
                    "units": "metric",
                    "forecast_range": "week",
                    "cache_version": 1,
                    "payload": '{"expired": true}',
                    "created_at": now - timedelta(hours=2),
                    "expires_at": now - timedelta(minutes=1),
                },
                {
                    "id": 12,
                    "lat": "45.500000",
                    "lon": "-122.600000",
                    "units": "metric",
                    "forecast_range": "week",
                    "cache_version": 2,
                    "payload": '{"valid": "older"}',
                    "created_at": now - timedelta(minutes=30),
                    "expires_at": now + timedelta(minutes=10),
                },
                {
                    "id": 13,
                    "lat": "45.500000",
                    "lon": "-122.600000",
                    "units": "metric",
                    "forecast_range": "week",
                    "cache_version": 3,
                    "payload": '{"valid": "newest"}',
                    "created_at": now - timedelta(minutes=5),
                    "expires_at": now + timedelta(minutes=30),
                },
                {
                    "id": 15,
                    "lat": "45.500000",
                    "lon": "-122.600000",
                    "units": "imperial",
                    "forecast_range": "week",
                    "cache_version": 99,
                    "payload": '{"other_units": true}',
                    "created_at": now,
                    "expires_at": now + timedelta(minutes=30),
                },
                {
                    "id": 16,
                    "lat": "45.500000",
                    "lon": "-122.600000",
                    "units": "metric",
                    "forecast_range": "day",
                    "cache_version": 99,
                    "payload": '{"other_range": true}',
                    "created_at": now,
                    "expires_at": now + timedelta(minutes=30),
                },
                {
                    "id": 17,
                    "lat": "45.500000",
                    "lon": "-122.600000",
                    "units": "metric",
                    "forecast_range": "week",
                    "cache_version": 4,
                    "payload": '{"boundary": true}',
                    "created_at": now,
                    "expires_at": now,
                },
            ],
        )

        row = fetch_latest_non_expired_weather_cache(
            connection,
            latitude="45.500000",
            longitude="-122.600000",
            units="metric",
            forecast_range="week",
            as_of=now,
        )

    assert row is not None
    assert row["id"] == 13
    assert row["cache_version"] == 3


def test_latest_non_expired_query_plan_prefers_weather_cache_index(postgres_engine) -> None:
    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    seed_sql = text(
        "INSERT INTO weather_cache (id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at) "
        "VALUES (:id, :lat, :lon, :units, :forecast_range, :cache_version, :payload, NOW(), NOW() + (:expires_minutes || ' minutes')::interval)"
    )

    seed_rows = []
    for item_id in range(100, 3100):
        seed_rows.append(
            {
                "id": item_id,
                "lat": str(40 + (item_id % 10)),
                "lon": str(-120 - (item_id % 10)),
                "units": "metric",
                "forecast_range": "day",
                "cache_version": (item_id % 4) + 1,
                "payload": '{"bulk": true}',
                "expires_minutes": (item_id % 240) + 1,
            }
        )

    seed_rows.extend(
        [
            {
                "id": 9001,
                "lat": "45.500000",
                "lon": "-122.600000",
                "units": "metric",
                "forecast_range": "week",
                "cache_version": 1,
                "payload": '{"expired": true}',
                "expires_minutes": -60,
            },
            {
                "id": 9002,
                "lat": "45.500000",
                "lon": "-122.600000",
                "units": "metric",
                "forecast_range": "week",
                "cache_version": 2,
                "payload": '{"fresh": true}',
                "expires_minutes": 60,
            },
        ]
    )

    with postgres_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE weather_cache"))
        connection.execute(seed_sql, seed_rows)

    explain_sql = text(
        "EXPLAIN (COSTS OFF) "
        "SELECT id FROM weather_cache "
        "WHERE latitude = :lat AND longitude = :lon AND units = :units AND forecast_range = :forecast_range "
        "AND expires_at > NOW() "
        "ORDER BY cache_version DESC, created_at DESC, id DESC LIMIT 1"
    )
    explain_analyze_sql = text(
        "EXPLAIN (ANALYZE, COSTS OFF, SUMMARY OFF, TIMING OFF) "
        "SELECT id FROM weather_cache "
        "WHERE latitude = :lat AND longitude = :lon AND units = :units AND forecast_range = :forecast_range "
        "AND expires_at > NOW() "
        "ORDER BY cache_version DESC, created_at DESC, id DESC LIMIT 1"
    )
    params = {
        "lat": "45.500000",
        "lon": "-122.600000",
        "units": "metric",
        "forecast_range": "week",
    }

    with postgres_engine.connect() as connection:
        connection.execute(text("SET enable_seqscan = off"))
        plan_lines = [row[0] for row in connection.execute(explain_sql, params)]
        analyze_lines = [row[0] for row in connection.execute(explain_analyze_sql, params)]

    explain_plan = _normalized_plan(" ".join(plan_lines))
    explain_analyze_plan = _normalized_plan(" ".join(analyze_lines))

    assert plan_lines
    assert analyze_lines

    scan_markers = ("Index Scan", "Index Only Scan", "Bitmap Index Scan")
    assert WEATHER_INDEX_NAME in explain_plan
    assert any(marker in explain_plan for marker in scan_markers)
    assert WEATHER_INDEX_NAME in explain_analyze_plan
    assert any(marker in explain_analyze_plan for marker in scan_markers)


def test_weather_cache_schema_documentation_is_present_and_accurate(postgres_engine) -> None:
    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    with postgres_engine.connect() as connection:
        table_comment = connection.execute(
            text(
                "SELECT obj_description('public.weather_cache'::regclass, 'pg_class')"
            )
        ).scalar_one()
        cache_version_comment = connection.execute(
            text(
                "SELECT col_description('public.weather_cache'::regclass, "
                "(SELECT attnum FROM pg_attribute WHERE attrelid = 'public.weather_cache'::regclass AND attname = 'cache_version'))"
            )
        ).scalar_one()
        expires_comment = connection.execute(
            text(
                "SELECT col_description('public.weather_cache'::regclass, "
                "(SELECT attnum FROM pg_attribute WHERE attrelid = 'public.weather_cache'::regclass AND attname = 'expires_at'))"
            )
        ).scalar_one()
        index_comment = connection.execute(
            text(
                "SELECT obj_description(indexrelid, 'pg_class') "
                "FROM pg_index WHERE indexrelid = 'ix_weather_cache_lookup_latest_non_expired'::regclass"
            )
        ).scalar_one()

    assert table_comment is not None
    assert "read-through weather cache" in table_comment.lower()
    assert cache_version_comment is not None
    assert "composite unique constraint" in cache_version_comment.lower()
    assert expires_comment is not None
    assert "ttl cutoff" in expires_comment.lower()
    assert index_comment is not None
    assert "latest non-expired" in index_comment.lower()
