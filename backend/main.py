from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import WeatherConfigError, load_weather_settings
from backend.weather_client import WeatherClient, WeatherServiceError

app = FastAPI(title="Weather App API", version="0.1.0")

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


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_non_empty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise _error(422, f"invalid_{field}", f"{field} must not be empty")
    return normalized


def _validate_range(range_value: str) -> str:
    normalized = _validate_non_empty(range_value, "range")
    if normalized != "day":
        raise _error(422, "invalid_range", "range must be 'day'")
    return normalized


def _validate_location(location: str) -> str:
    return _validate_non_empty(location, "location")


def _map_weather_error(exc: WeatherServiceError) -> HTTPException:
    if exc.kind == "timeout":
        return _error(504, "upstream_timeout", "Weather provider timed out")
    if exc.kind == "provider_rejected":
        return _error(502, "upstream_rejected", "Weather provider rejected request")
    if exc.kind == "malformed_response":
        return _error(502, "upstream_malformed_response", "Weather provider returned invalid data")
    return _error(502, "upstream_failure", "Unable to fetch weather data")


def _to_canonical_response(forecast: dict[str, Any]) -> CanonicalWeatherResponse:
    location = forecast.get("location") if isinstance(forecast, dict) else None
    forecast_days = forecast.get("forecast") if isinstance(forecast, dict) else None

    if not isinstance(location, dict) or not isinstance(forecast_days, list) or not forecast_days:
        raise _error(502, "upstream_malformed_response", "Weather provider returned invalid data")

    day0 = forecast_days[0]
    if not isinstance(day0, dict):
        raise _error(502, "upstream_malformed_response", "Weather provider returned invalid data")

    temperature_payload = day0.get("temperature")
    condition_payload = day0.get("condition")
    if not isinstance(temperature_payload, dict) or not isinstance(condition_payload, dict):
        raise _error(502, "upstream_malformed_response", "Weather provider returned invalid data")

    city = location.get("name")
    avg_temperature = temperature_payload.get("avg")
    description = condition_payload.get("text")

    if not isinstance(city, str) or not city.strip() or not isinstance(description, str) or not description.strip():
        raise _error(502, "upstream_malformed_response", "Weather provider returned invalid data")
    if not isinstance(avg_temperature, (int, float)):
        raise _error(502, "upstream_malformed_response", "Weather provider returned invalid data")

    return CanonicalWeatherResponse(
        data=CanonicalWeatherData(
            city=city,
            temperature=float(avg_temperature),
            description=description,
        )
    )


async def _fetch_forecast(days: int, location: str, units: str, weather_client: WeatherClient) -> dict[str, Any]:
    try:
        return await weather_client.fetch_forecast(location=location, days=days, units=units)
    except WeatherServiceError as exc:
        raise _map_weather_error(exc) from exc


async def _legacy_forecast_response(
    days: int,
    location: str,
    units: str,
    weather_client: WeatherClient,
) -> dict[str, object]:
    validated_location = _validate_location(location)
    data = await _fetch_forecast(days=days, location=validated_location, units=units, weather_client=weather_client)
    return {"data": data, "source": "weatherapi"}


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
    response_model=CanonicalWeatherResponse,
    responses={
        200: {
            "description": "Normalized canonical day weather payload",
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
    range: Optional[str] = Query(
        None,
        description="Required by contract. Must be exactly day for the canonical endpoint.",
        examples=["day"],
    ),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> CanonicalWeatherResponse:
    if city is None:
        raise _error(400, "missing_city", "city query parameter is required")
    if range is None:
        raise _error(400, "missing_range", "range query parameter is required")

    _validate_range(range)
    validated_city = _validate_non_empty(city, "city")
    forecast = await _fetch_forecast(days=1, location=validated_city, units="metric", weather_client=weather_client)
    return _to_canonical_response(forecast)


@app.get(
    "/api/weather/day",
    summary="Legacy day weather endpoint",
    description=LEGACY_DAY_DESCRIPTION,
    response_description="Legacy weather payload wrapped as { data, source }",
    deprecated=True,
)
async def weather_day(
    response: Response,
    location: str = Query(
        ...,
        min_length=1,
        description="Legacy parameter. Map this location value to canonical city during migration.",
    ),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    response.headers["Link"] = '</api/weather?city={city}&range=day>; rel="successor-version"'
    return await _legacy_forecast_response(days=1, location=location, units=units, weather_client=weather_client)


@app.get("/api/weather/3day")
async def weather_three_day(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _legacy_forecast_response(days=3, location=location, units=units, weather_client=weather_client)


@app.get("/api/weather/week")
async def weather_week(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _legacy_forecast_response(days=7, location=location, units=units, weather_client=weather_client)


if __name__ == "__main__":
    raise SystemExit(main())
