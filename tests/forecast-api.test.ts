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

test("resolveApiBaseUrl prioritizes explicit config over environment", () => {
  const endpoint = resolveApiBaseUrl("https://override.example.com", {
    VITE_API_BASE_URL: "https://api.example.com",
    VITE_BACKEND_URL: "https://legacy.example.com",
  });

  assert.equal(endpoint, "https://override.example.com");
});

test("buildForecastRequest includes backend base URL, location, and selected range", () => {
  const endpoint = buildForecastRequest({ location: "Paris", range: "three-day" });

  assert.equal(endpoint, "http://localhost:8000/api/weather?city=Paris&range=three-day");
});

test("buildForecastRequest includes coordinates when available", () => {
  const endpoint = buildForecastRequest({
    location: "48.857, 2.352",
    range: "day",
    coordinates: { lat: 48.857, lon: 2.352 },
  });

  assert.equal(
    endpoint,
    "http://localhost:8000/api/weather?city=48.857%2C+2.352&range=day&lat=48.857&lon=2.352",
  );
});

test("buildForecastRequest respects configured backend base URL", () => {
  const endpoint = buildForecastRequest(
    { location: "Paris", range: "day" },
    { apiBaseUrl: "https://api.example.com/" },
  );

  assert.equal(endpoint, "https://api.example.com/api/weather?city=Paris&range=day");
});

test("fetchForecast calls backend endpoint contract with expected method and path", async () => {
  const calls: string[] = [];
  const fakeFetch: typeof fetch = async (input: RequestInfo | URL) => {
    calls.push(String(input));

    return new Response(
      JSON.stringify({
        data: {
          city: "Paris",
          temperature: 20,
          description: "clear sky",
          units: "metric",
        },
        source: "openweathermap",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };

  const result = await fetchForecast({ location: "Paris", range: "day" }, fakeFetch, {
    apiBaseUrl: "http://127.0.0.1:8000",
  });

  assert.equal(result.locationLabel, "Paris");
  assert.equal(result.range, "day");
  assert.equal(result.weather.city, "Paris");
  assert.equal(result.source, "openweathermap");
  assert.equal(calls.length, 1);
  assert.equal(calls[0], "http://127.0.0.1:8000/api/weather?city=Paris&range=day");
});

test("fetchForecast fails fast on misconfigured backend base URL", async () => {
  const fakeFetch: typeof fetch = async () => {
    throw new Error("fetch should not run");
  };

  await assert.rejects(
    () => fetchForecast({ location: "Paris", range: "day" }, fakeFetch, { apiBaseUrl: "backend.local" }),
    /VITE_API_BASE_URL must be an absolute URL/,
  );
});

test("fetchForecast surfaces backend error details", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(JSON.stringify({ detail: "upstream unavailable" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  };

  await assert.rejects(
    () => fetchForecast({ location: "Paris", range: "day" }, fakeFetch),
    /upstream unavailable/,
  );
});

test("fetchForecast rejects malformed data", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(JSON.stringify({ data: { city: "Paris" } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await assert.rejects(
    () => fetchForecast({ location: "Paris", range: "day" }, fakeFetch),
    /malformed forecast data/,
  );
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
