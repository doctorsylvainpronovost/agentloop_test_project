import unittest

import httpx
from fastapi.testclient import TestClient

from backend.main import app, get_weather_client
from backend.weather_client import WeatherClient, WeatherServiceError


class FakeWeatherClient:
    async def fetch_weather(self, city: str, units: str = "metric"):
        return {
            "city": city,
            "temperature": 21.5,
            "description": "clear sky",
            "units": units,
        }


class FailingWeatherClient:
    async def fetch_weather(self, city: str, units: str = "metric"):
        raise WeatherServiceError("upstream unavailable")


class WeatherApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_weather_endpoint_happy_path(self):
        app.dependency_overrides[get_weather_client] = lambda: FakeWeatherClient()
        response = self.client.get("/api/weather", params={"city": "Paris", "units": "metric"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["city"], "Paris")
        self.assertEqual(body["data"]["units"], "metric")
        self.assertEqual(body["source"], "openweathermap")

    def test_weather_endpoint_upstream_error(self):
        app.dependency_overrides[get_weather_client] = lambda: FailingWeatherClient()
        response = self.client.get("/api/weather", params={"city": "Paris"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "upstream unavailable")


class WeatherClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_weather_normalizes_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "name": "Berlin",
                    "main": {"temp": 18.0},
                    "weather": [{"description": "few clouds"}],
                },
            )

        transport = httpx.MockTransport(handler)
        client = WeatherClient(api_key="test-key", base_url="https://api.example.com", transport=transport)

        payload = await client.fetch_weather(city="Berlin", units="metric")

        self.assertEqual(payload["city"], "Berlin")
        self.assertEqual(payload["temperature"], 18.0)
        self.assertEqual(payload["description"], "few clouds")

    async def test_fetch_weather_handles_upstream_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"message": "service unavailable"})

        transport = httpx.MockTransport(handler)
        client = WeatherClient(api_key="test-key", base_url="https://api.example.com", transport=transport)

        with self.assertRaises(WeatherServiceError) as ctx:
            await client.fetch_weather(city="Rome")

        self.assertIn("status 503", str(ctx.exception))

    async def test_fetch_weather_requires_api_key(self):
        client = WeatherClient(api_key="")

        with self.assertRaises(WeatherServiceError) as ctx:
            await client.fetch_weather(city="Madrid")

        self.assertIn("WEATHER_API_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
