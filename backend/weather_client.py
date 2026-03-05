from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class WeatherServiceError(Exception):
    """Raised when weather data cannot be fetched or normalized."""

    def __init__(self, message: str, *, kind: str = "upstream_error") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class WeatherClient:
    api_key: str
    base_url: str
    timeout: float = 10.0
    transport: httpx.BaseTransport | None = None

    async def fetch_forecast(
        self,
        location: str,
        days: int,
        units: str = "metric",
    ) -> dict[str, Any]:
        if not self.api_key:
            raise WeatherServiceError("WEATHER_API_KEY is not configured", kind="configuration")

        endpoint = f"{self.base_url.rstrip('/')}/forecast.json"
        params = {
            "key": self.api_key,
            "q": location,
            "days": days,
            "aqi": "no",
            "alerts": "no",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise WeatherServiceError("Weather API request timed out", kind="timeout") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 401, 403, 404}:
                raise WeatherServiceError(
                    "Weather provider rejected the request",
                    kind="provider_rejected",
                ) from exc
            raise WeatherServiceError("Weather API request failed", kind="upstream_error") from exc
        except httpx.RequestError as exc:
            raise WeatherServiceError("Unable to reach weather API", kind="upstream_error") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherServiceError("Malformed weather API response", kind="malformed_response") from exc

        return normalize_forecast_payload(payload=payload, days=days, units=units)


def normalize_forecast_payload(payload: dict[str, Any], days: int, units: str) -> dict[str, Any]:
    try:
        location_payload = payload["location"]
        forecast_days = payload["forecast"]["forecastday"]
    except (KeyError, TypeError) as exc:
        raise WeatherServiceError("Malformed weather API response", kind="malformed_response") from exc

    if not isinstance(forecast_days, list) or len(forecast_days) < days:
        raise WeatherServiceError("Malformed weather API response", kind="malformed_response")

    normalized_days: list[dict[str, Any]] = []
    for day_payload in forecast_days[:days]:
        day_summary = day_payload.get("day", {}) if isinstance(day_payload, dict) else {}
        condition = day_summary.get("condition", {}) if isinstance(day_summary, dict) else {}

        normalized_days.append(
            {
                "date": day_payload.get("date"),
                "temperature": {
                    "min": day_summary.get("mintemp_c"),
                    "max": day_summary.get("maxtemp_c"),
                    "avg": day_summary.get("avgtemp_c"),
                },
                "condition": {
                    "text": condition.get("text"),
                    "icon": condition.get("icon"),
                },
                "wind_kph": day_summary.get("maxwind_kph"),
                "humidity": day_summary.get("avghumidity"),
                "precip_mm": day_summary.get("totalprecip_mm", 0.0),
                "chance_of_rain": day_summary.get("daily_chance_of_rain", 0),
            }
        )

    return {
        "location": {
            "name": location_payload.get("name"),
            "region": location_payload.get("region"),
            "country": location_payload.get("country"),
            "lat": location_payload.get("lat"),
            "lon": location_payload.get("lon"),
            "timezone": location_payload.get("tz_id"),
        },
        "units": units,
        "requested_days": days,
        "forecast": normalized_days,
    }
