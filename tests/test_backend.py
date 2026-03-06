import unittest

import httpx
from fastapi.testclient import TestClient

from backend.config import WeatherConfigError, load_weather_settings
from backend.main import app, get_weather_client
from backend.weather_client import WeatherClient, WeatherServiceError, normalize_forecast_payload


class FakeForecastClient:
    async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
        return {
            "location": {"name": location, "country": "Testland"},
            "units": units,
            "requested_days": days,
            "forecast": [
                {
                    "date": f"2026-03-0{i + 1}",
                    "temperature": {"min": 7.0 + i, "max": 15.0 + i, "avg": 11.0 + i},
                    "condition": {"text": "Sunny" if i == 0 else "Cloudy"},
                }
                for i in range(days)
            ],
        }


class FailingForecastClient:
    def __init__(self, kind: str):
        self.kind = kind

    async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
        raise WeatherServiceError("upstream failure", kind=self.kind)


class WeatherApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_weather_range_day_returns_normalized_payload(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather", params={"city": "Paris", "range": "day"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"data": {"city": "Paris", "temperature": 11.0, "description": "Sunny"}},
        )

    def test_weather_range_non_day_keeps_existing_contract(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather", params={"city": "Paris", "range": "3day"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "weatherapi")
        self.assertEqual(body["data"]["location"]["name"], "Paris")
        self.assertEqual(body["data"]["requested_days"], 3)
        self.assertEqual(len(body["data"]["forecast"]), 3)

    def test_weather_requires_city(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_city")

    def test_weather_rejects_blank_city(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather", params={"city": "   ", "range": "day"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_city")

    def test_weather_rejects_unsupported_range(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather", params={"city": "Paris", "range": "month"})

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "invalid_range")
        self.assertIn("day", detail["message"])
        self.assertIn("3day", detail["message"])
        self.assertIn("week", detail["message"])

    def test_legacy_day_endpoint_maps_location_alias(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather/day", params={"location": "Paris", "units": "metric"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "weatherapi")
        self.assertEqual(body["data"]["location"]["name"], "Paris")
        self.assertEqual(body["data"]["requested_days"], 1)

    def test_legacy_day_endpoint_requires_location(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather/day")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_location")

    def test_forecast_endpoints_happy_path(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        endpoint_days = {
            "/api/weather/day": 1,
            "/api/weather/3day": 3,
            "/api/weather/week": 7,
        }
        for endpoint, expected_days in endpoint_days.items():
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint, params={"location": "Paris", "units": "metric"})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["source"], "weatherapi")
                self.assertEqual(body["data"]["location"]["name"], "Paris")
                self.assertEqual(body["data"]["requested_days"], expected_days)
                self.assertEqual(len(body["data"]["forecast"]), expected_days)

    def test_forecast_endpoints_require_location(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        for endpoint in ("/api/weather/day", "/api/weather/3day", "/api/weather/week"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 422)

    def test_forecast_endpoints_reject_blank_location(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather/day", params={"location": "   "})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_location")

    def test_forecast_endpoints_map_upstream_errors_consistently(self):
        scenarios = {
            "timeout": (504, "upstream_timeout"),
            "provider_rejected": (502, "upstream_rejected"),
            "malformed_response": (502, "upstream_malformed_response"),
            "upstream_error": (502, "upstream_failure"),
        }

        for kind, (status_code, code) in scenarios.items():
            app.dependency_overrides[get_weather_client] = lambda kind=kind: FailingForecastClient(kind)
            for endpoint in ("/api/weather", "/api/weather/day", "/api/weather/3day", "/api/weather/week"):
                with self.subTest(kind=kind, endpoint=endpoint):
                    params = {"city": "Paris", "range": "day"} if endpoint == "/api/weather" else {"location": "Paris"}
                    response = self.client.get(endpoint, params=params)
                    self.assertEqual(response.status_code, status_code)
                    self.assertEqual(response.json()["detail"]["code"], code)


class WeatherConfigTestCase(unittest.TestCase):
    def test_load_weather_settings_requires_api_key(self):
        with self.assertRaises(WeatherConfigError) as ctx:
            load_weather_settings({"WEATHER_BASE_URL": "https://api.weatherapi.com/v1"})

        self.assertIn("WEATHER_API_KEY", str(ctx.exception))

    def test_load_weather_settings_requires_base_url(self):
        with self.assertRaises(WeatherConfigError) as ctx:
            load_weather_settings({"WEATHER_API_KEY": "test-key", "WEATHER_BASE_URL": ""})

        self.assertIn("WEATHER_BASE_URL", str(ctx.exception))

    def test_load_weather_settings_loads_valid_values(self):
        settings = load_weather_settings(
            {
                "WEATHER_API_KEY": "test-key",
                "WEATHER_BASE_URL": "https://api.weatherapi.com/v1",
            }
        )

        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.base_url, "https://api.weatherapi.com/v1")


class WeatherClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_forecast_normalizes_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params["q"], "Berlin")
            self.assertEqual(request.url.params["days"], "3")
            return httpx.Response(
                200,
                json={
                    "location": {
                        "name": "Berlin",
                        "region": "Berlin",
                        "country": "Germany",
                        "lat": 52.52,
                        "lon": 13.41,
                        "tz_id": "Europe/Berlin",
                    },
                    "forecast": {
                        "forecastday": [
                            {
                                "date": "2026-03-01",
                                "day": {
                                    "mintemp_c": 7.0,
                                    "maxtemp_c": 15.0,
                                    "avgtemp_c": 11.0,
                                    "condition": {"text": "Sunny", "icon": "//icon.png"},
                                    "maxwind_kph": 12.0,
                                    "avghumidity": 66,
                                    "totalprecip_mm": 0.0,
                                    "daily_chance_of_rain": 0,
                                },
                            },
                            {
                                "date": "2026-03-02",
                                "day": {
                                    "mintemp_c": 8.0,
                                    "maxtemp_c": 16.0,
                                    "avgtemp_c": 12.0,
                                    "condition": {"text": "Cloudy", "icon": "//icon2.png"},
                                    "maxwind_kph": 10.0,
                                    "avghumidity": 70,
                                    "totalprecip_mm": 0.4,
                                    "daily_chance_of_rain": 25,
                                },
                            },
                            {
                                "date": "2026-03-03",
                                "day": {
                                    "mintemp_c": 6.0,
                                    "maxtemp_c": 13.0,
                                    "avgtemp_c": 9.0,
                                    "condition": {"text": "Rain", "icon": "//icon3.png"},
                                    "maxwind_kph": 16.0,
                                    "avghumidity": 80,
                                    "totalprecip_mm": 3.3,
                                    "daily_chance_of_rain": 85,
                                },
                            },
                        ]
                    },
                },
            )

        transport = httpx.MockTransport(handler)
        client = WeatherClient(
            api_key="test-key",
            base_url="https://api.weatherapi.com/v1",
            transport=transport,
        )

        payload = await client.fetch_forecast(location="Berlin", days=3, units="metric")

        self.assertEqual(payload["location"]["name"], "Berlin")
        self.assertEqual(payload["requested_days"], 3)
        self.assertEqual(len(payload["forecast"]), 3)
        self.assertEqual(payload["forecast"][0]["condition"]["text"], "Sunny")

    async def test_fetch_forecast_handles_provider_rejection(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "Invalid query"}})

        transport = httpx.MockTransport(handler)
        client = WeatherClient(
            api_key="test-key",
            base_url="https://api.weatherapi.com/v1",
            transport=transport,
        )

        with self.assertRaises(WeatherServiceError) as ctx:
            await client.fetch_forecast(location="?", days=1)

        self.assertEqual(ctx.exception.kind, "provider_rejected")

    async def test_fetch_forecast_handles_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        transport = httpx.MockTransport(handler)
        client = WeatherClient(
            api_key="test-key",
            base_url="https://api.weatherapi.com/v1",
            transport=transport,
        )

        with self.assertRaises(WeatherServiceError) as ctx:
            await client.fetch_forecast(location="Madrid", days=1)

        self.assertEqual(ctx.exception.kind, "timeout")

    async def test_fetch_forecast_handles_malformed_payload(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"location": {"name": "Rome"}})

        transport = httpx.MockTransport(handler)
        client = WeatherClient(
            api_key="test-key",
            base_url="https://api.weatherapi.com/v1",
            transport=transport,
        )

        with self.assertRaises(WeatherServiceError) as ctx:
            await client.fetch_forecast(location="Rome", days=1)

        self.assertEqual(ctx.exception.kind, "malformed_response")

    async def test_fetch_forecast_requires_api_key(self):
        client = WeatherClient(api_key="", base_url="https://api.weatherapi.com/v1")

        with self.assertRaises(WeatherServiceError) as ctx:
            await client.fetch_forecast(location="Madrid", days=1)

        self.assertIn("WEATHER_API_KEY", str(ctx.exception))


class ForecastNormalizationTestCase(unittest.TestCase):
    def test_normalize_forecast_payload_limits_to_requested_days(self):
        payload = {
            "location": {"name": "Lisbon", "country": "Portugal"},
            "forecast": {
                "forecastday": [
                    {"date": "2026-03-01", "day": {"condition": {"text": "Clear", "icon": None}}},
                    {"date": "2026-03-02", "day": {"condition": {"text": "Rain", "icon": None}}},
                    {"date": "2026-03-03", "day": {"condition": {"text": "Cloudy", "icon": None}}},
                ]
            },
        }

        normalized = normalize_forecast_payload(payload=payload, days=1, units="metric")

        self.assertEqual(normalized["requested_days"], 1)
        self.assertEqual(len(normalized["forecast"]), 1)

    def test_normalize_forecast_payload_graceful_defaults(self):
        payload = {
            "location": {"name": "Oslo", "country": "Norway"},
            "forecast": {"forecastday": [{"date": "2026-03-01", "day": {"condition": {}}}]},
        }

        normalized = normalize_forecast_payload(payload=payload, days=1, units="metric")

        day = normalized["forecast"][0]
        self.assertEqual(day["precip_mm"], 0.0)
        self.assertEqual(day["chance_of_rain"], 0)


if __name__ == "__main__":
    unittest.main()
