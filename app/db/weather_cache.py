from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

LATEST_NON_EXPIRED_WEATHER_CACHE_SQL = text(
    """
    SELECT id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at
    FROM weather_cache
    WHERE latitude = :latitude
      AND longitude = :longitude
      AND units = :units
      AND forecast_range = :forecast_range
      AND expires_at > :as_of
    ORDER BY cache_version DESC, created_at DESC, id DESC
    LIMIT 1
    """
)


def fetch_latest_non_expired_weather_cache(
    connection: Connection,
    *,
    latitude: Decimal | str,
    longitude: Decimal | str,
    units: str,
    forecast_range: str,
    as_of: datetime | None = None,
) -> RowMapping | None:
    effective_as_of = as_of or datetime.now(timezone.utc)
    result = connection.execute(
        LATEST_NON_EXPIRED_WEATHER_CACHE_SQL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "units": units,
            "forecast_range": forecast_range,
            "as_of": effective_as_of,
        },
    )
    return result.mappings().first()
