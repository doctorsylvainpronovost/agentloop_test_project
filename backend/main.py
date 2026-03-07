from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import WeatherConfigError, load_weather_settings
from backend.weather_client import WeatherClient, WeatherServiceError

app = FastAPI(title="Weather App API", version="0.1.0")

RANGE_TO_DAYS = {
    "day": 1,
    "3day": 3,
    "week": 7,
}

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

CACHE_TTL_SECONDS = 900


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
    print("Backend scaffold is running.")
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


def _cache_database_path() -> Path:
    configured = os.getenv("WEATHER_CACHE_DB_PATH", "app.db").strip()
    if configured:
        return Path(configured)
    return Path("app.db")


def _cache_connection() -> sqlite3.Connection:
    db_path = _cache_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_key TEXT NOT NULL,
            forecast_range TEXT NOT NULL,
            units TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            UNIQUE(city_key, forecast_range, units)
        )
        """
    )
    return connection


def _cache_lookup(city: str, forecast_range: str, units: str) -> Optional[dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    city_key = city.strip().lower()

    with _cache_connection() as connection:
        row = connection.execute(
            """
            SELECT status_code, payload
            FROM weather_cache
            WHERE city_key = ?
              AND forecast_range = ?
              AND units = ?
              AND expires_at > ?
            LIMIT 1
            """,
            (city_key, forecast_range, units, now_iso),
        ).fetchone()

    if row is None:
        return None

    return {
        "status_code": int(row["status_code"]),
        "payload": json.loads(str(row["payload"])),
    }


def _cache_store(city: str, forecast_range: str, units: str, status_code: int, payload: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=CACHE_TTL_SECONDS)
    city_key = city.strip().lower()

    with _cache_connection() as connection:
        connection.execute(
            """
            INSERT INTO weather_cache (city_key, forecast_range, units, status_code, payload, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_key, forecast_range, units)
            DO UPDATE SET
                status_code = excluded.status_code,
                payload = excluded.payload,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (
                city_key,
                forecast_range,
                units,
                status_code,
                json.dumps(payload),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        connection.commit()


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


async def _fetch_weather_forecast(
    *,
    city: Optional[str],
    range_value: str,
    units: str,
    weather_client: WeatherClient,
    city_field_name: str,
) -> Tuple[str, dict[str, Any]]:
    validated_city = _validate_required_query(city, field_name=city_field_name)
    validated_range = _validate_range(range_value)

    try:
        data = await weather_client.fetch_forecast(
            location=validated_city,
            days=RANGE_TO_DAYS[validated_range],
            units=units,
        )
    except WeatherServiceError as exc:
        raise _map_weather_error(exc) from exc

    return validated_range, data


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
) -> dict[str, Any]:
    validated_city = _validate_required_query(city, field_name="city")
    validated_range = _validate_range(range)

    cache_hit = _cache_lookup(validated_city, validated_range, units)
    if cache_hit is not None and cache_hit["status_code"] == 200:
        return cache_hit["payload"]

    try:
        forecast_payload = await weather_client.fetch_forecast(
            location=validated_city,
            days=RANGE_TO_DAYS[validated_range],
            units=units,
        )
    except WeatherServiceError as exc:
        raise _map_weather_error(exc) from exc

    if validated_range == "day":
        response_payload = _normalize_day_payload(forecast_payload)
    else:
        response_payload = {"data": forecast_payload, "source": "weatherapi"}

    _cache_store(validated_city, validated_range, units, 200, response_payload)
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
) -> dict[str, Any]:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    response.headers["Link"] = '</api/weather?city={city}&range=day>; rel="successor-version"'

    _, forecast_payload = await _fetch_weather_forecast(
        city=location,
        range_value="day",
        units=units,
        weather_client=weather_client,
        city_field_name="location",
    )

    return {"data": forecast_payload, "source": "weatherapi"}


@app.get("/api/weather/3day")
async def weather_three_day(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    _, forecast_payload = await _fetch_weather_forecast(
        city=location,
        range_value="3day",
        units=units,
        weather_client=weather_client,
        city_field_name="location",
    )
    return {"data": forecast_payload, "source": "weatherapi"}


@app.get("/api/weather/week")
async def weather_week(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    _, forecast_payload = await _fetch_weather_forecast(
        city=location,
        range_value="week",
        units=units,
        weather_client=weather_client,
        city_field_name="location",
    )
    return {"data": forecast_payload, "source": "weatherapi"}


if __name__ == "__main__":
    raise SystemExit(main())
