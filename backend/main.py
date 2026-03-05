from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Query

from backend.weather_client import WeatherClient, WeatherServiceError

app = FastAPI(title="Weather App API", version="0.1.0")


def get_weather_client() -> WeatherClient:
    return WeatherClient(api_key=os.getenv("WEATHER_API_KEY", ""))


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Weather API scaffold is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/weather")
async def weather(
    city: str = Query(..., min_length=1),
    units: str = Query("metric", pattern="^(metric|imperial)$"),
    weather_client: WeatherClient = Depends(get_weather_client),
) -> dict[str, object]:
    try:
        weather_data = await weather_client.fetch_weather(city=city, units=units)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "data": weather_data,
        "source": "openweathermap",
    }
