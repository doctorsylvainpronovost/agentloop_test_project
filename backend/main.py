from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import WeatherConfigError, load_weather_settings
from backend.weather_client import WeatherClient, WeatherServiceError

MESSAGE = "Backend scaffold is running."
RANGE_TO_DAYS = {"day": 1, "three-day": 3, "week": 7}

app = FastAPI(title="Weather App API", version="0.1.0")


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


def _validate_location(location: str) -> str:
    normalized = location.strip()
    if not normalized:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_location", "message": "location must not be empty"},
        )
    return normalized


def _map_weather_error(exc: WeatherServiceError) -> HTTPException:
    if exc.kind == "timeout":
        return HTTPException(
            status_code=504,
            detail={"code": "upstream_timeout", "message": "Weather provider timed out"},
        )
    if exc.kind == "provider_rejected":
        return HTTPException(
            status_code=502,
            detail={"code": "upstream_rejected", "message": "Weather provider rejected request"},
        )
    if exc.kind == "malformed_response":
        return HTTPException(
            status_code=502,
            detail={
                "code": "upstream_malformed_response",
                "message": "Weather provider returned invalid data",
            },
        )
    return HTTPException(
        status_code=502,
        detail={"code": "upstream_failure", "message": "Unable to fetch weather data"},
    )


def _normalize_day_weather_payload(payload: dict[str, object]) -> dict[str, object]:
    location = payload.get("location") if isinstance(payload, dict) else {}
    forecast = payload.get("forecast") if isinstance(payload, dict) else []

    first_day: dict[str, object] = {}
    if isinstance(forecast, list) and forecast:
        maybe_first_day = forecast[0]
        if isinstance(maybe_first_day, dict):
            first_day = maybe_first_day

    temperature = first_day.get("temperature") if isinstance(first_day, dict) else {}
    condition = first_day.get("condition") if isinstance(first_day, dict) else {}

    city = ""
    if isinstance(location, dict):
        raw_city = location.get("name")
        if isinstance(raw_city, str):
            city = raw_city

    avg_temperature = None
    if isinstance(temperature, dict):
        avg_temperature = temperature.get("avg")

    description = ""
    if isinstance(condition, dict):
        raw_description = condition.get("text")
        if isinstance(raw_description, str):
            description = raw_description

    return {
        "city": city,
        "temperature": avg_temperature,
        "description": description,
    }


async def _fetch_forecast(days: int, city: str, units: str, weather_client: WeatherClient) -> dict[str, object]:
    validated_city = _validate_location(city)

    try:
        return await weather_client.fetch_forecast(location=validated_city, days=days, units=units)
    except WeatherServiceError as exc:
        raise _map_weather_error(exc) from exc


async def _canonical_weather_response(
    city: str,
    range_value: str,
    units: str,
    weather_client: WeatherClient,
) -> dict[str, object]:
    days = RANGE_TO_DAYS[range_value]
    forecast = await _fetch_forecast(days=days, city=city, units=units, weather_client=weather_client)

    return {"data": _normalize_day_weather_payload(forecast)}


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Weather API scaffold is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/weather")
async def weather(
    city: str = Query(..., min_length=1),
    range_value: str = Query(..., alias="range", pattern="^(day|three-day|week)$"),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    del lat
    del lon
    return await _canonical_weather_response(
        city=city,
        range_value=range_value,
        units=units,
        weather_client=weather_client,
    )


@app.get("/api/weather/day", deprecated=True)
async def weather_day(
    location: Optional[str] = Query(None, min_length=1),
    city: Optional[str] = Query(None, min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> JSONResponse:
    resolved_city = city if city is not None else location
    if resolved_city is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "missing_city", "message": "city query parameter is required"},
        )

    payload = await _canonical_weather_response(
        city=resolved_city,
        range_value="day",
        units=units,
        weather_client=weather_client,
    )
    return JSONResponse(
        content=payload,
        headers={"Deprecation": "true", "X-Deprecated-Endpoint": "/api/weather/day"},
    )


@app.get("/api/weather/3day")
async def weather_three_day(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _canonical_weather_response(
        city=location,
        range_value="three-day",
        units=units,
        weather_client=weather_client,
    )


@app.get("/api/weather/week")
async def weather_week(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _canonical_weather_response(
        city=location,
        range_value="week",
        units=units,
        weather_client=weather_client,
    )


if __name__ == "__main__":
    raise SystemExit(main())
