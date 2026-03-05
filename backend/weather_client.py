from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class WeatherServiceError(Exception):
    """Raised when weather data cannot be fetched or normalized."""


@dataclass
class WeatherClient:
    api_key: str
    base_url: str = "https://api.openweathermap.org/data/2.5/weather"
    timeout: float = 10.0
    transport: httpx.BaseTransport | None = None

    async def fetch_weather(self, city: str, units: str = "metric") -> dict[str, Any]:
        if not self.api_key:
            raise WeatherServiceError("WEATHER_API_KEY is not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.get(
                    self.base_url,
                    params={"q": city, "units": units, "appid": self.api_key},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise WeatherServiceError("Weather API request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise WeatherServiceError(
                f"Upstream weather API returned status {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise WeatherServiceError("Unable to reach weather API") from exc

        payload = response.json()

        try:
            normalized = {
                "city": payload["name"],
                "temperature": payload["main"]["temp"],
                "description": payload["weather"][0]["description"],
                "units": units,
            }
        except (KeyError, IndexError, TypeError) as exc:
            raise WeatherServiceError("Malformed weather API response") from exc

        return normalized
