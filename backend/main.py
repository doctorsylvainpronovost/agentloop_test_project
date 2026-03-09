#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.weather_cache import fetch_latest_non_expired_weather_cache
from backend.config import WeatherConfigError, load_weather_settings
from backend.weather_client import WeatherClient, WeatherServiceError

app = FastAPI(title="Weather App API", version="0.1.0")

RANGE_TO_DAYS = {
    "day": 1,
    "3day": 3,
    "week": 7,
}
CACHE_TTL_MINUTES = 30
COORDINATE_SCALE = Decimal("0.000001")

CANONICAL_WEATHER_DESCRIPTION = (
    "Canonical weather contract for day forecasts. "
    "Clients must send a non-empty city value and range=day. "
    "If either parameter is missing, this endpoint returns a deterministic 400 error payload."
)

LEGACY_DAY_DESCRIPTION = (
    "Legacy day endpoint kept for backward compatibility and marked deprecated. "
    "Existing consumers may continue to call this route until 2026-12-31. "
    "Migrate requests by mapping location -> city and calling /api/weather?city=<city>&range=day "
    "to receive the normalized canonical day response schema."
)

MESSAGE = "Backend scaffold is running."

CACHE_TTL_SECONDS = 10 * 60
DEFAULT_CACHE_DB_PATH = Path(__file__).resolve().parents[1] / ".weather_cache.sqlite3"


def _get_cache_database_path() -> str:
    configured = os.getenv("WEATHER_CACHE_DB", "").strip()
    if configured:
        return configured
    return str(DEFAULT_CACHE_DB_PATH)


def _ensure_cache_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            forecast_range TEXT NOT NULL,
            units TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            UNIQUE(city, forecast_range, units)
        )
        """
    )
    connection.commit()


def get_cache_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_get_cache_database_path(), check_same_thread=False)
    try:
        _ensure_cache_schema(connection)
        yield connection
    finally:
        connection.close()


def _normalize_cache_city(city: str) -> str:
    return city.strip().lower()


def _read_weather_cache(
    connection: sqlite3.Connection,
    *,
    city: str,
    range_value: str,
    units: str,
) -> dict[str, Any] | None:
    _ensure_cache_schema(connection)
    row = connection.execute(
        """
        SELECT payload
        FROM weather_cache
        WHERE city = ? AND forecast_range = ? AND units = ? AND expires_at > ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalize_cache_city(city), range_value, units, int(time.time())),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def _write_weather_cache(
    connection: sqlite3.Connection,
    *,
    city: str,
    range_value: str,
    units: str,
    payload: dict[str, Any],
) -> None:
    _ensure_cache_schema(connection)
    now = int(time.time())
    connection.execute(
        """
        INSERT INTO weather_cache (city, forecast_range, units, payload, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(city, forecast_range, units)
        DO UPDATE SET
            payload = excluded.payload,
            created_at = excluded.created_at,
            expires_at = excluded.expires_at
        """,
        (
            _normalize_cache_city(city),
            range_value,
            units,
            json.dumps(payload),
            now,
            now + CACHE_TTL_SECONDS,
        ),
    )
    connection.commit()


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable error detail")


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class CanonicalWeatherData(BaseModel):
    city: str = Field(..., description="Resolved city name", examples=["London"])
    temperature: float = Field(..., description="Average day temperature in Celsius", examples=[11.5])
    description: str = Field(..., description="Text summary of day conditions", examples=["Partly cloudy"])


class CanonicalWeatherResponse(BaseModel):
    data: CanonicalWeatherData = Field(..., description="Normalized canonical day forecast payload")


def main() -> int:
    """Run backend scaffold entrypoint."""
    print(MESSAGE)
    return 0


def get_weather_client() -> WeatherClient:
    try:
        settings = load_weather_settings()
    except WeatherConfigError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "weather_not_configured",
                "message": "Weather service is not configured",
            },
        ) from exc

    return WeatherClient(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.timeout)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_required_query(value: Optional[str], *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise _error(
            422,
            f"invalid_{field_name}",
            f"{field_name} query parameter is required and must not be empty",
        )
    return normalized


def _validate_range(range_value: str) -> str:
    normalized = range_value.strip().lower()
    if normalized not in RANGE_TO_DAYS:
        allowed = ", ".join(RANGE_TO_DAYS.keys())
        raise _error(422, "invalid_range", f"range must be one of: {allowed}")
    return normalized


def _map_weather_error(exc: WeatherServiceError) -> HTTPException:
    if exc.kind == "timeout":
        return _error(504, "upstream_timeout", "Weather provider timed out")
    if exc.kind == "provider_rejected":
        return _error(502, "upstream_rejected", "Weather provider rejected request")
    if exc.kind == "malformed_response":
        return _error(502, "upstream_malformed_response", "Weather provider returned invalid data")
    return _error(502, "upstream_failure", "Unable to fetch weather data")


def _normalize_day_payload(forecast_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    location = forecast_payload.get("location")
    forecast = forecast_payload.get("forecast")

    if not isinstance(location, dict) or not isinstance(forecast, list) or not forecast:
        raise _map_weather_error(WeatherServiceError("Malformed weather API response", kind="malformed_response"))

    day = forecast[0] if isinstance(forecast[0], dict) else {}
    temperature = day.get("temperature", {}) if isinstance(day.get("temperature"), dict) else {}
    condition = day.get("condition", {}) if isinstance(day.get("condition"), dict) else {}

    average_temperature = temperature.get("avg")
    if average_temperature is None:
        average_temperature = temperature.get("max")
    if average_temperature is None:
        average_temperature = temperature.get("min")

    return {
        "data": {
            "city": location.get("name"),
            "temperature": average_temperature,
            "description": condition.get("text"),
        }
    }


def _cache_coordinates_from_city(city: str) -> Tuple[Decimal, Decimal]:
    digest = hashlib.sha256(city.encode("utf-8")).digest()

    latitude_bucket = int.from_bytes(digest[:8], "big") % 180000001
    longitude_bucket = int.from_bytes(digest[8:16], "big") % 360000001

    latitude = (Decimal(latitude_bucket) / Decimal("1000000") - Decimal("90")).quantize(COORDINATE_SCALE)
    longitude = (Decimal(longitude_bucket) / Decimal("1000000") - Decimal("180")).quantize(COORDINATE_SCALE)
    return latitude, longitude


def _get_cache_database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


def _read_cached_forecast(*, city: str, range_value: str, units: str) -> Optional[dict[str, Any]]:
    database_url = _get_cache_database_url()
    if not database_url:
        return None

    latitude, longitude = _cache_coordinates_from_city(city)

    engine_kwargs: dict[str, Any] = {"future": True}
    if database_url.lower().startswith("postgresql"):
        engine_kwargs["connect_args"] = {"connect_timeout": 1}

    try:
        engine = create_engine(database_url, **engine_kwargs)
        try:
            with engine.connect() as connection:
                row = fetch_latest_non_expired_weather_cache(
                    connection,
                    latitude=str(latitude),
                    longitude=str(longitude),
                    units=units,
                    forecast_range=range_value,
                    as_of=datetime.utcnow(),
                )
        finally:
            engine.dispose()
    except SQLAlchemyError:
        return None

    if row is None:
        return None

    payload = row.get("payload")
    if not isinstance(payload, str):
        return None

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _persist_cached_forecast(*, city: str, range_value: str, units: str, payload: dict[str, Any]) -> None:
    database_url = _get_cache_database_url()
    if not database_url:
        return

    latitude, longitude = _cache_coordinates_from_city(city)
    latitude_value = str(latitude)
    longitude_value = str(longitude)
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=CACHE_TTL_MINUTES)
    serialized_payload = json.dumps(payload)

    engine_kwargs: dict[str, Any] = {"future": True}
    if database_url.lower().startswith("postgresql"):
        engine_kwargs["connect_args"] = {"connect_timeout": 1}

    try:
        engine = create_engine(database_url, **engine_kwargs)
        try:
            with engine.begin() as connection:
                next_id = connection.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM weather_cache")).scalar_one()
                next_version = connection.execute(
                    text(
                        "SELECT COALESCE(MAX(cache_version), 0) + 1 "
                        "FROM weather_cache "
                        "WHERE latitude = :latitude "
                        "AND longitude = :longitude "
                        "AND units = :units "
                        "AND forecast_range = :forecast_range"
                    ),
                    {
                        "latitude": latitude_value,
                        "longitude": longitude_value,
                        "units": units,
                        "forecast_range": range_value,
                    },
                ).scalar_one()
                connection.execute(
                    text(
                        "INSERT INTO weather_cache "
                        "(id, latitude, longitude, units, forecast_range, cache_version, payload, created_at, expires_at) "
                        "VALUES "
                        "(:id, :latitude, :longitude, :units, :forecast_range, :cache_version, :payload, :created_at, :expires_at)"
                    ),
                    {
                        "id": int(next_id),
                        "latitude": latitude_value,
                        "longitude": longitude_value,
                        "units": units,
                        "forecast_range": range_value,
                        "cache_version": int(next_version),
                        "payload": serialized_payload,
                        "created_at": now,
                        "expires_at": expires_at,
                    },
                )
        finally:
            engine.dispose()
    except SQLAlchemyError:
        return


def _build_weather_response(validated_range: str, forecast_payload: dict[str, Any]) -> dict[str, Any]:
    if validated_range == "day":
        return _normalize_day_payload(forecast_payload)
    return {"data": forecast_payload, "source": "weatherapi"}


async def _fetch_weather_forecast(
    *,
    city: Optional[str],
    range_value: str,
    units: str,
    weather_client: WeatherClient,
    cache_connection: sqlite3.Connection,
    city_field_name: str,
) -> Tuple[str, str, dict[str, Any], bool]:
    validated_city = _validate_required_query(city, field_name=city_field_name)
    validated_range = _validate_range(range_value)

    cached_payload = _read_weather_cache(
        cache_connection,
        city=validated_city,
        range_value=validated_range,
        units=units,
    )
    if cached_payload is not None:
        return validated_city, validated_range, cached_payload, True

    try:
        data = await weather_client.fetch_forecast(
            location=validated_city,
            days=RANGE_TO_DAYS[validated_range],
            units=units,
        )
    except WeatherServiceError as exc:
        raise _map_weather_error(exc) from exc

    _write_weather_cache(
        cache_connection,
        city=validated_city,
        range_value=validated_range,
        units=units,
        payload=data,
    )

    return validated_city, validated_range, data, False


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Weather API scaffold is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/api/weather",
    summary="Canonical day weather endpoint",
    description=CANONICAL_WEATHER_DESCRIPTION,
    response_description="Normalized day weather response payload",
    responses={
        200: {
            "description": "Normalized canonical day weather payload",
            "model": CanonicalWeatherResponse,
            "content": {
                "application/json": {
                    "example": {
                        "data": {
                            "city": "London",
                            "temperature": 11.5,
                            "description": "Partly cloudy",
                        }
                    }
                }
            },
        },
        400: {"description": "Required query parameter is missing", "model": ErrorResponse},
        422: {"description": "Query parameter is invalid", "model": ErrorResponse},
        502: {"description": "Upstream provider failure", "model": ErrorResponse},
        504: {"description": "Upstream provider timeout", "model": ErrorResponse},
    },
)
async def weather(
    city: Optional[str] = Query(
        None,
        description="Required by contract. Use the city name that replaces legacy location.",
        examples=["London"],
    ),
    range: str = Query(
        "day",
        description="Required by contract. Must be exactly day for the canonical endpoint.",
        examples=["day"],
    ),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
    cache_connection: sqlite3.Connection = Depends(get_cache_connection),
) -> dict[str, Any]:
    validated_city, validated_range, forecast_payload, served_from_cache = await _fetch_weather_forecast(
        city=city,
        range_value=range,
        units=units,
        weather_client=weather_client,
        cache_connection=cache_connection,
        city_field_name="city",
    )

    response_payload = _build_weather_response(validated_range, forecast_payload)
    if not served_from_cache:
        _persist_cached_forecast(city=validated_city, range_value=validated_range, units=units, payload=forecast_payload)
    return response_payload


@app.get(
    "/api/weather/day",
    summary="Legacy day weather endpoint",
    description=LEGACY_DAY_DESCRIPTION,
    response_description="Legacy weather payload wrapped as { data, source }",
    deprecated=True,
)
async def weather_day(
    response: Response,
    location: Optional[str] = Query(
        None,
        description="Legacy parameter. Map this location value to canonical city during migration.",
    ),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
    cache_connection: sqlite3.Connection = Depends(get_cache_connection),
) -> dict[str, Any]:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    response.headers["Link"] = '</api/weather?city={city}&range=day>; rel="successor-version"'

    validated_city, validated_range, forecast_payload, served_from_cache = await _fetch_weather_forecast(
        city=location,
        range_value="day",
        units=units,
        weather_client=weather_client,
        cache_connection=cache_connection,
        city_field_name="location",
    )

    response_payload = {"data": forecast_payload, "source": "weatherapi"}
    if not served_from_cache:
        _persist_cached_forecast(city=validated_city, range_value=validated_range, units=units, payload=forecast_payload)
    return response_payload


@app.get("/api/weather/3day")
async def weather_three_day(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
    cache_connection: sqlite3.Connection = Depends(get_cache_connection),
) -> dict[str, object]:
    validated_city, validated_range, forecast_payload, served_from_cache = await _fetch_weather_forecast(
        city=location,
        range_value="3day",
        units=units,
        weather_client=weather_client,
        cache_connection=cache_connection,
        city_field_name="location",
    )
    response_payload = {"data": forecast_payload, "source": "weatherapi"}
    if not served_from_cache:
        _persist_cached_forecast(city=validated_city, range_value=validated_range, units=units, payload=forecast_payload)
    return response_payload


@app.get("/api/weather/week")
async def weather_week(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
    cache_connection: sqlite3.Connection = Depends(get_cache_connection),
) -> dict[str, object]:
    validated_city, validated_range, forecast_payload, served_from_cache = await _fetch_weather_forecast(
        city=location,
        range_value="week",
        units=units,
        weather_client=weather_client,
        cache_connection=cache_connection,
        city_field_name="location",
    )
    response_payload = {"data": forecast_payload, "source": "weatherapi"}
    if not served_from_cache:
        _persist_cached_forecast(city=validated_city, range_value=validated_range, units=units, payload=forecast_payload)
    return response_payload


if __name__ == "__main__":
    raise SystemExit(main())
