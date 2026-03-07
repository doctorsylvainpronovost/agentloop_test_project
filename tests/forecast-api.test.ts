import assert from "node:assert/strict";
import test from "node:test";

import {
  buildForecastRequest,
  fetchForecast,
  ForecastApiError,
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

test("buildForecastRequest maps range to normalized backend paths", () => {
  const dayEndpoint = buildForecastRequest({ location: "Paris", range: "day" });
  const threeDayEndpoint = buildForecastRequest({ location: "Paris", range: "three-day" });
  const weekEndpoint = buildForecastRequest({ location: "Paris", range: "week" });

  assert.equal(dayEndpoint, "http://localhost:8000/api/weather/day?location=Paris&units=metric");
  assert.equal(threeDayEndpoint, "http://localhost:8000/api/weather/3day?location=Paris&units=metric");
  assert.equal(weekEndpoint, "http://localhost:8000/api/weather/week?location=Paris&units=metric");
});

test("buildForecastRequest includes coordinates when available", () => {
  const endpoint = buildForecastRequest({
    location: "48.857, 2.352",
    range: "day",
    coordinates: { lat: 48.857, lon: 2.352 },
  });

  assert.equal(
    endpoint,
    "http://localhost:8000/api/weather/day?location=48.857%2C+2.352&units=metric&lat=48.857&lon=2.352",
  );
});

test("fetchForecast normalizes both canonical schema and legacy payloads", async () => {
  const cases = [
    {
      name: "canonical normalized response",
      payload: {
        data: {
          location: {
            name: "Paris",
          },
          units: "metric",
          requested_days: 1,
          forecast: [
            {
              date: "2026-03-05",
              temperature: { min: 15, max: 21, avg: 18 },
              condition: { text: "Partly cloudy" },
            },
          ],
        },
        source: "weatherapi",
      },
      expected: {
        city: "Paris",
        temperature: 18,
        description: "Partly cloudy",
        units: "metric",
        source: "weatherapi",
      },
    },
    {
      name: "legacy response",
      payload: {
        data: {
          city: "Madrid",
          temperature: 25,
          description: "Sunny",
          units: "imperial",
        },
        source: "legacy",
      },
      expected: {
        city: "Madrid",
        temperature: 25,
        description: "Sunny",
        units: "imperial",
        source: "legacy",
      },
    },
  ];

  for (const sample of cases) {
    const fakeFetch: typeof fetch = async () => {
      return new Response(JSON.stringify(sample.payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const result = await fetchForecast({ location: sample.expected.city, range: "day" }, fakeFetch);
    assert.equal(result.weather.city, sample.expected.city, sample.name);
    assert.equal(result.weather.temperature, sample.expected.temperature, sample.name);
    assert.equal(result.weather.description, sample.expected.description, sample.name);
    assert.equal(result.weather.units, sample.expected.units, sample.name);
    assert.equal(result.source, sample.expected.source, sample.name);
  }
});

test("fetchForecast rejects malformed success payloads deterministically", async () => {
  const malformedPayloads = [
    { data: null },
    { data: { location: { name: "Paris" }, forecast: [], units: "metric" } },
    {
      data: {
        location: { name: "Paris" },
        forecast: [{ temperature: { avg: "warm" }, condition: { text: "clear" } }],
        units: "metric",
      },
    },
  ];

  for (const payload of malformedPayloads) {
    const fakeFetch: typeof fetch = async () => {
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    await assert.rejects(() => fetchForecast({ location: "Paris", range: "day" }, fakeFetch), /malformed forecast data/);
  }
});

test("fetchForecast maps validation error arrays to ForecastApiError", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(
      JSON.stringify({
        detail: [
          { loc: ["query", "location"], msg: "location must not be empty" },
          { loc: ["query", "units"], msg: "Input should be metric or imperial" },
        ],
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );
  };

  await assert.rejects(
    () => fetchForecast({ location: "Paris", range: "day" }, fakeFetch),
    (error: unknown) => {
      assert.ok(error instanceof ForecastApiError);
      assert.equal(error.status, 422);
      assert.deepEqual(error.validationErrors?.fieldErrors.location, ["location must not be empty"]);
      assert.deepEqual(error.validationErrors?.fieldErrors.units, ["Input should be metric or imperial"]);
      return true;
    },
  );
});

test("fetchForecast maps detail object validation errors with fallback message", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(
      JSON.stringify({
        detail: {
          errors: {
            location: ["Location is required"],
          },
          non_field_errors: ["Please fix the highlighted fields"],
        },
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );
  };

  await assert.rejects(
    () => fetchForecast({ location: "Paris", range: "day" }, fakeFetch),
    (error: unknown) => {
      assert.ok(error instanceof ForecastApiError);
      assert.deepEqual(error.validationErrors?.fieldErrors.location, ["Location is required"]);
      assert.deepEqual(error.validationErrors?.generalErrors, ["Please fix the highlighted fields"]);
      return true;
    },
  );
});

test("fetchForecast surfaces upstream message for non-validation failures", async () => {
  const fakeFetch: typeof fetch = async () => {
    return new Response(JSON.stringify({ detail: { message: "Weather provider timed out" } }), {
      status: 504,
      headers: { "Content-Type": "application/json" },
    });
  };

  await assert.rejects(() => fetchForecast({ location: "Paris", range: "day" }, fakeFetch), /Weather provider timed out/);
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
