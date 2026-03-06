from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel

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


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class CanonicalWeatherData(BaseModel):
    city: str
    temperature: float
    description: str


class CanonicalWeatherResponse(BaseModel):
    data: CanonicalWeatherData


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


@app.get("/api/weather")
async def weather(
    city: Optional[str] = Query(None),
    range: str = Query("day"),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, Any]:
    validated_range, forecast_payload = await _fetch_weather_forecast(
        city=city,
        range_value=range,
        units=units,
        weather_client=weather_client,
        city_field_name="city",
    )

    if validated_range == "day":
        return _normalize_day_payload(forecast_payload)

    return {"data": forecast_payload, "source": "weatherapi"}


@app.get("/api/weather/day")
async def weather_day(
    response: Response,
    location: Optional[str] = Query(None),
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
