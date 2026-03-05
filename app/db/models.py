import sqlalchemy as sa

from app.db.base import Base

VALID_WEATHER_UNITS = frozenset({"metric", "imperial"})
VALID_FORECAST_RANGES = frozenset({"1d", "3d", "7d"})

weather_cache = sa.Table(
    "weather_cache",
    Base.metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("lat", sa.Float, nullable=False),
    sa.Column("lon", sa.Float, nullable=False),
    sa.Column("units", sa.String(length=16), nullable=False),
    sa.Column("range", sa.String(length=16), nullable=False),
    sa.Column("payload", sa.JSON, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def validate_weather_cache_key(units: str, forecast_range: str) -> None:
    if units not in VALID_WEATHER_UNITS:
        raise ValueError(f"units must be one of {sorted(VALID_WEATHER_UNITS)}")
    if forecast_range not in VALID_FORECAST_RANGES:
        raise ValueError(f"range must be one of {sorted(VALID_FORECAST_RANGES)}")


def build_weather_cache_lookup_query(
    lat: float,
    lon: float,
    units: str,
    forecast_range: str,
) -> sa.Select:
    validate_weather_cache_key(units=units, forecast_range=forecast_range)
    return (
        sa.select(weather_cache)
        .where(
            weather_cache.c.lat == lat,
            weather_cache.c.lon == lon,
            weather_cache.c.units == units,
            weather_cache.c.range == forecast_range,
            weather_cache.c.expires_at > sa.func.now(),
        )
        .order_by(weather_cache.c.created_at.desc())
        .limit(1)
    )


__all__ = [
    "Base",
    "VALID_FORECAST_RANGES",
    "VALID_WEATHER_UNITS",
    "build_weather_cache_lookup_query",
    "validate_weather_cache_key",
    "weather_cache",
]
