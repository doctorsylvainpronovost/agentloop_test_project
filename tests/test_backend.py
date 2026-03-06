import unittest
from pathlib import Path

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
                    "temperature": {"avg": 11.5 + i, "min": 6 + i, "max": 16 + i},
                    "condition": {"text": "Clear" if i == 0 else "Cloudy", "icon": "//icon.png"},
                }
                for i in range(days)
            ],
        }


class FailingForecastClient:
    def __init__(self, kind: str):
        self.kind = kind

    async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
        raise WeatherServiceError("upstream failure", kind=self.kind)


class MalformedForecastClient:
    async def fetch_forecast(self, location: str, days: int, units: str = "metric"):
        return {"location": {"name": location}, "forecast": []}


class WeatherApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_canonical_weather_happy_path(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather", params={"city": "Paris", "range": "day"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "data": {
                    "city": "Paris",
                    "temperature": 11.5,
                    "description": "Clear",
                }
            },
        )

    def test_canonical_weather_validation_errors(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        scenarios = [
            ({"range": "day"}, 400, "missing_city", "city query parameter is required"),
            ({"city": "Paris"}, 400, "missing_range", "range query parameter is required"),
            ({"city": "Paris", "range": "week"}, 422, "invalid_range", "range must be 'day'"),
            ({"city": "   ", "range": "day"}, 422, "invalid_city", "city must not be empty"),
            ({"city": "Paris", "range": "   "}, 422, "invalid_range", "range must not be empty"),
        ]

        for params, status_code, code, message in scenarios:
            with self.subTest(params=params):
                response = self.client.get("/api/weather", params=params)
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json(), {"detail": {"code": code, "message": message}})

    def test_canonical_weather_maps_upstream_errors_consistently(self):
        scenarios = {
            "timeout": (504, "upstream_timeout"),
            "provider_rejected": (502, "upstream_rejected"),
            "malformed_response": (502, "upstream_malformed_response"),
            "upstream_error": (502, "upstream_failure"),
        }

        for kind, (status_code, code) in scenarios.items():
            app.dependency_overrides[get_weather_client] = lambda kind=kind: FailingForecastClient(kind)
            response = self.client.get("/api/weather", params={"city": "Paris", "range": "day"})
            with self.subTest(kind=kind):
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json()["detail"]["code"], code)

    def test_canonical_weather_rejects_malformed_provider_payload(self):
        app.dependency_overrides[get_weather_client] = lambda: MalformedForecastClient()

        response = self.client.get("/api/weather", params={"city": "Paris", "range": "day"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "upstream_malformed_response")

    def test_legacy_forecast_endpoints_happy_path(self):
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

    def test_legacy_day_endpoint_returns_deprecation_headers(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather/day", params={"location": "Paris"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("deprecation"), "true")
        self.assertEqual(response.headers.get("sunset"), "Wed, 31 Dec 2026 23:59:59 GMT")
        self.assertIn('/api/weather?city={city}&range=day', response.headers.get("link", ""))

    def test_legacy_forecast_endpoints_require_location(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        for endpoint in ("/api/weather/day", "/api/weather/3day", "/api/weather/week"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 422)

    def test_legacy_forecast_endpoints_reject_blank_location(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeForecastClient()

        response = self.client.get("/api/weather/day", params={"location": "   "})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_location")

    def test_legacy_forecast_endpoints_map_upstream_errors_consistently(self):
        scenarios = {
            "timeout": (504, "upstream_timeout"),
            "provider_rejected": (502, "upstream_rejected"),
            "malformed_response": (502, "upstream_malformed_response"),
            "upstream_error": (502, "upstream_failure"),
        }

        for kind, (status_code, code) in scenarios.items():
            app.dependency_overrides[get_weather_client] = lambda kind=kind: FailingForecastClient(kind)
            for endpoint in ("/api/weather/day", "/api/weather/3day", "/api/weather/week"):
                with self.subTest(kind=kind, endpoint=endpoint):
                    response = self.client.get(endpoint, params={"location": "Paris"})
                    self.assertEqual(response.status_code, status_code)
                    self.assertEqual(response.json()["detail"]["code"], code)


class WeatherOpenApiContractTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_openapi_documents_canonical_day_endpoint_and_response_schema(self):
        schema = self.client.get("/openapi.json").json()
        weather_operation = schema["paths"]["/api/weather"]["get"]

        self.assertIn("Canonical weather contract", weather_operation["description"])
        params = {parameter["name"]: parameter for parameter in weather_operation["parameters"]}
        self.assertIn("city", params)
        self.assertIn("range", params)
        self.assertEqual(params["city"]["required"], False)
        self.assertEqual(params["range"]["required"], False)
        self.assertIn("replaces legacy location", params["city"]["description"])
        self.assertIn("Must be exactly day", params["range"]["description"])

        canonical_example = weather_operation["responses"]["200"]["content"]["application/json"]["example"]
        self.assertEqual(canonical_example["data"]["city"], "London")
        self.assertIsInstance(canonical_example["data"]["temperature"], float)
        self.assertEqual(canonical_example["data"]["description"], "Partly cloudy")

        canonical_data_schema = schema["components"]["schemas"]["CanonicalWeatherData"]
        self.assertEqual(canonical_data_schema["required"], ["city", "temperature", "description"])
        self.assertEqual(canonical_data_schema["properties"]["city"]["type"], "string")
        self.assertEqual(canonical_data_schema["properties"]["temperature"]["type"], "number")
        self.assertEqual(canonical_data_schema["properties"]["description"]["type"], "string")

    def test_openapi_marks_legacy_day_endpoint_deprecated_with_migration_guidance(self):
        schema = self.client.get("/openapi.json").json()
        legacy_operation = schema["paths"]["/api/weather/day"]["get"]

        self.assertEqual(legacy_operation["deprecated"], True)
        self.assertIn("Legacy day weather endpoint", legacy_operation["summary"])
        self.assertIn("mapping location -> city", legacy_operation["description"])
        self.assertIn("range=day", legacy_operation["description"])
        params = {parameter["name"]: parameter for parameter in legacy_operation["parameters"]}
        self.assertIn("location", params["location"]["description"])
        self.assertIn("canonical city", params["location"]["description"])


class WeatherContractDocumentationParityTestCase(unittest.TestCase):
    def test_readme_includes_canonical_examples(self):
        readme_path = Path(__file__).resolve().parents[1] / "README.md"
        content = readme_path.read_text(encoding="utf-8")

        required_snippets = [
            "GET /api/weather?city=London&range=day",
            '"code": "missing_city"',
            '"code": "missing_range"',
            '"code": "invalid_range"',
            '"code": "invalid_city"',
            "GET /api/weather/day?location=London",
            "Deprecation: true",
            "deprecated-but-preserved",
            "location -> city",
            "canonical day response",
        ]

        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, content)


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
