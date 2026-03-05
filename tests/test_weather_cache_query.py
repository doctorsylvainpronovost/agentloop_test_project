from sqlalchemy.dialects import postgresql

from app.db.models import build_weather_cache_lookup_query, validate_weather_cache_key


def _compile_postgres_sql() -> str:
    query = build_weather_cache_lookup_query(
        lat=40.7128,
        lon=-74.0060,
        units="metric",
        forecast_range="3d",
    )
    compiled = query.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)


def test_lookup_query_matches_indexed_access_pattern() -> None:
    sql = _compile_postgres_sql()

    assert "FROM weather_cache" in sql
    assert "weather_cache.lat = 40.7128" in sql
    assert "weather_cache.lon = -74.006" in sql
    assert "weather_cache.units = 'metric'" in sql
    assert "weather_cache.range = '3d'" in sql
    assert "weather_cache.expires_at > now()" in sql
    assert "ORDER BY weather_cache.created_at DESC" in sql
    assert "LIMIT 1" in sql


def test_lookup_query_validation_rejects_invalid_units() -> None:
    try:
        validate_weather_cache_key(units="kelvin", forecast_range="1d")
    except ValueError as error:
        assert "units must be one of" in str(error)
    else:
        raise AssertionError("Expected invalid units to raise ValueError")


def test_lookup_query_validation_rejects_invalid_range() -> None:
    try:
        validate_weather_cache_key(units="metric", forecast_range="month")
    except ValueError as error:
        assert "range must be one of" in str(error)
    else:
        raise AssertionError("Expected invalid range to raise ValueError")
