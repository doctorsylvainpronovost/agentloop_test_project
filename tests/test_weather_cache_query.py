from app.db.weather_cache import LATEST_NON_EXPIRED_WEATHER_CACHE_SQL


def test_weather_cache_latest_query_orders_by_version_then_recency() -> None:
    sql = str(LATEST_NON_EXPIRED_WEATHER_CACHE_SQL)

    assert "ORDER BY cache_version DESC, created_at DESC, id DESC" in sql
    assert "expires_at > :as_of" in sql
