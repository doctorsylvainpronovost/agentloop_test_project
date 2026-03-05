from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query

from backend.config import WeatherConfigError, load_weather_settings
from backend.weather_client import WeatherClient, WeatherServiceError

app = FastAPI(title="Weather App API", version="0.1.0")


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


async def _forecast_response(
    days: int,
    location: str,
    units: str,
    weather_client: WeatherClient,
) -> dict[str, object]:
    validated_location = _validate_location(location)

    try:
        data = await weather_client.fetch_forecast(location=validated_location, days=days, units=units)
    except WeatherServiceError as exc:
        raise _map_weather_error(exc) from exc

    return {"data": data, "source": "weatherapi"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Weather API scaffold is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/weather/day")
async def weather_day(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _forecast_response(days=1, location=location, units=units, weather_client=weather_client)


@app.get("/api/weather/3day")
async def weather_three_day(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _forecast_response(days=3, location=location, units=units, weather_client=weather_client)


@app.get("/api/weather/week")
async def weather_week(
    location: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    return await _forecast_response(days=7, location=location, units=units, weather_client=weather_client)
