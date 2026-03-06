import assert from "node:assert/strict";
import test from "node:test";

import {
  buildForecastRequest,
  fetchForecast,
  formatCoordinateLabel,
  getCurrentCoordinates,
  resolveApiBaseUrl,
} from "../src/forecastApi";

test("resolveApiBaseUrl uses localhost backend when env is missing", () => {
  assert.equal(resolveApiBaseUrl(undefined), "http://localhost:8000");
  assert.equal(resolveApiBaseUrl("   "), "http://localhost:8000");
});

test("resolveApiBaseUrl trims trailing slash and validates absolute URL", () => {
  assert.equal(resolveApiBaseUrl("http://localhost:8000/"), "http://localhost:8000");
  assert.throws(() => resolveApiBaseUrl("/api"), /VITE_API_BASE_URL must be an absolute URL/);
});

test("resolveApiBaseUrl supports legacy backend env variable names", () => {
  assert.equal(resolveApiBaseUrl(undefined, { VITE_BACKEND_URL: "https://legacy.example.com/" }), "https://legacy.example.com");
  assert.equal(
    resolveApiBaseUrl(undefined, { VITE_BACKEND_BASE_URL: "https://base.example.com/" }),
    "https://base.example.com",
  );
});

test("buildForecastRequest always uses canonical weather endpoint query", () => {
  const endpoint = buildForecastRequest({ location: " New York " });

  assert.equal(endpoint, "http://localhost:8000/api/weather?city=New+York&range=day");
});

test("buildForecastRequest respects configured backend base URL", () => {
  const endpoint = buildForecastRequest({ location: "Paris" }, { apiBaseUrl: "https://api.example.com/" });

  assert.equal(endpoint, "https://api.example.com/api/weather?city=Paris&range=day");
});

test("fetchForecast uses GET and canonical endpoint", async () => {
  const calls: Array<{ input: string; method: string }> = [];
  const fakeFetch: typeof fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input: String(input), method: init?.method ?? "GET" });

    return new Response(
      JSON.stringify({
        data: {
          city: "Paris",
          temperature: 20,
          description: "clear sky",
        },
        source: "weatherapi",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };

  const result = await fetchForecast({ location: "Paris" }, fakeFetch, {
    apiBaseUrl: "http://127.0.0.1:8000",
  });

  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.data.locationLabel, "Paris");
    assert.equal(result.data.weather.city, "Paris");
    assert.equal(result.data.weather.temperature, 20);
    assert.equal(result.data.weather.description, "clear sky");
  }
  assert.deepEqual(calls, [{ input: "http://127.0.0.1:8000/api/weather?city=Paris&range=day", method: "GET" }]);
});

test("fetchForecast classifies backend 4xx responses as validation errors", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(JSON.stringify({ detail: { code: "invalid_location", message: "location must not be empty" } }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await fetchForecast({ location: "Paris" }, fakeFetch);

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.error.kind, "validation");
    assert.equal(result.error.statusCode, 422);
    assert.equal(result.error.message, "location must not be empty");
  }
});

test("fetchForecast uses fallback validation message when backend response body is unexpected", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response("{}", {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await fetchForecast({ location: "Paris" }, fakeFetch);

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.error.kind, "validation");
    assert.equal(result.error.message, "Weather request was invalid. Please verify the city name and try again.");
  }
});

test("fetchForecast classifies network failures", async () => {
  const fakeFetch: typeof fetch = async () => {
    throw new Error("socket hang up");
  };

  const result = await fetchForecast({ location: "Paris" }, fakeFetch);

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.error.kind, "network");
    assert.equal(result.error.message, "Network error while fetching weather. Please check your connection and retry.");
  }
});

test("fetchForecast classifies malformed success payloads", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(JSON.stringify({ data: { city: "Paris" } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await fetchForecast({ location: "Paris" }, fakeFetch);

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.error.kind, "malformed-payload");
    assert.equal(result.error.message, "Weather data was malformed. Please try again later.");
  }
});

test("fetchForecast rejects empty locations as validation", async () => {
  const fakeFetch: typeof fetch = async () => {
    throw new Error("fetch should not run");
  };

  const result = await fetchForecast({ location: " " }, fakeFetch);

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.error.kind, "validation");
    assert.equal(result.error.message, "Please enter a location before requesting weather.");
  }
});

test("getCurrentCoordinates resolves when browser geolocation succeeds", async () => {
  const geolocation: Geolocation = {
    clearWatch: () => undefined,
    watchPosition: () => 1,
    getCurrentPosition: (success) => {
      success({
        coords: {
          latitude: 40.7128,
          longitude: -74.006,
          accuracy: 1,
          altitude: null,
          altitudeAccuracy: null,
          heading: null,
          speed: null,
          toJSON: () => ({}),
        },
        timestamp: Date.now(),
        toJSON: () => ({}),
      });
    },
  };

  const coords = await getCurrentCoordinates(geolocation);

  assert.deepEqual(coords, { lat: 40.7128, lon: -74.006 });
});

test("getCurrentCoordinates handles permission denied and timeout errors", async () => {
  const deniedGeolocation: Geolocation = {
    clearWatch: () => undefined,
    watchPosition: () => 1,
    getCurrentPosition: (_success, error) => {
      error?.({ code: 1, message: "denied", PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
    },
  };

  await assert.rejects(() => getCurrentCoordinates(deniedGeolocation), /Location access was denied/);

  const timeoutGeolocation: Geolocation = {
    clearWatch: () => undefined,
    watchPosition: () => 1,
    getCurrentPosition: (_success, error) => {
      error?.({ code: 3, message: "timeout", PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
    },
  };

  await assert.rejects(() => getCurrentCoordinates(timeoutGeolocation), /timed out/);
});

test("formatCoordinateLabel keeps location readable", () => {
  assert.equal(formatCoordinateLabel({ lat: 37.7749, lon: -122.4194 }), "37.775, -122.419");
});
