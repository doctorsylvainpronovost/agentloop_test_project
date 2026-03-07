from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class WeatherConfigError(Exception):
    """Raised when required weather configuration values are missing."""


@dataclass(frozen=True)
class WeatherSettings:
    api_key: str
    base_url: str
    timeout: float = 10.0


def load_weather_settings(environ: Mapping[str, str] | None = None) -> WeatherSettings:
    values = os.environ if environ is None else environ
    api_key = values.get("WEATHER_API_KEY", "").strip()
    base_url = values.get("WEATHER_BASE_URL", "https://api.weatherapi.com/v1").strip()

    if not api_key:
        raise WeatherConfigError("WEATHER_API_KEY is required")
    if not base_url:
        raise WeatherConfigError("WEATHER_BASE_URL is required")

    return WeatherSettings(api_key=api_key, base_url=base_url)
