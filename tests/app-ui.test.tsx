import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { JSDOM } from "jsdom";

import App from "../src/App";

const setupDom = () => {
  const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
    url: "http://localhost",
  });

  Object.defineProperty(globalThis, "window", { configurable: true, value: dom.window });
  Object.defineProperty(globalThis, "document", { configurable: true, value: dom.window.document });
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  Object.defineProperty(globalThis, "HTMLElement", { configurable: true, value: dom.window.HTMLElement });
  Object.defineProperty(globalThis, "Event", { configurable: true, value: dom.window.Event });
  Object.defineProperty(globalThis, "MouseEvent", { configurable: true, value: dom.window.MouseEvent });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, value: true });

  return dom;
};

const flush = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const setInputValue = async (input: HTMLInputElement, value: string): Promise<void> => {
  await act(async () => {
    const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value");
    descriptor?.set?.call(input, value);
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    await flush();
  });
};

const submitForm = async (): Promise<void> => {
  const form = document.querySelector("form") as HTMLFormElement;
  await act(async () => {
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await flush();
    await flush();
  });
};

let dom: JSDOM;
let root: Root;
let container: HTMLElement;
let originalFetch: typeof fetch;

beforeEach(async () => {
  dom = setupDom();
  originalFetch = globalThis.fetch;
  container = document.querySelector("#root") as HTMLElement;
  root = createRoot(container);

  await act(async () => {
    root.render(<App />);
  });
});

afterEach(async () => {
  await act(async () => {
    root.unmount();
  });

  globalThis.fetch = originalFetch;
  dom.window.close();
});

test("renders location controls and initial weather hint", () => {
  assert.ok(document.querySelector("#location-input"));
  assert.ok(document.querySelector('button[type="button"]'));
  assert.ok(document.body.textContent?.includes("Weather details appear here after a request."));
});

test("shows local validation error when manual location is empty", async () => {
  await submitForm();

  assert.ok(document.body.textContent?.includes("Please enter a location before requesting weather."));
});

test("renders successful normalized weather response", async () => {
  globalThis.fetch = (async () => {
    return new Response(
      JSON.stringify({
        data: {
          city: "Berlin",
          temperature: 18,
          description: "cloudy",
        },
        source: "weatherapi",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Berlin");
  await submitForm();

  assert.ok(document.body.textContent?.includes("Requested for: Berlin"));
  assert.ok(document.body.textContent?.includes("City: Berlin"));
  assert.ok(document.body.textContent?.includes("Temperature: 18"));
  assert.ok(document.body.textContent?.includes("Conditions: cloudy"));
});

test("surfaces backend 4xx validation errors from API detail body", async () => {
  globalThis.fetch = (async () => {
    return new Response(JSON.stringify({ detail: { code: "invalid_location", message: "location must not be empty" } }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Invalid");
  await submitForm();

  assert.ok(document.body.textContent?.includes("location must not be empty"));
});

test("shows stable fallback message when backend payload is malformed", async () => {
  globalThis.fetch = (async () => {
    return new Response(JSON.stringify({ data: null }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Paris");
  await submitForm();

  assert.ok(document.body.textContent?.includes("Weather data was malformed. Please try again later."));
});

test("shows network failure message without crashing", async () => {
  globalThis.fetch = (async () => {
    throw new Error("network down");
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Paris");
  await submitForm();

  assert.ok(document.body.textContent?.includes("Network error while fetching weather. Please check your connection and retry."));
});

test("auto-detect requests canonical city+day query and handles geolocation errors", async () => {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(
      JSON.stringify({
        data: {
          city: "Detected City",
          temperature: 17,
          description: "breeze",
        },
        source: "weatherapi",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;

  const geolocationSuccess: Geolocation = {
    clearWatch: () => undefined,
    watchPosition: () => 1,
    getCurrentPosition: (success) => {
      success({
        coords: {
          latitude: 34.0522,
          longitude: -118.2437,
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

  Object.defineProperty(globalThis.navigator, "geolocation", {
    configurable: true,
    value: geolocationSuccess,
  });

  const detectButton = Array.from(document.querySelectorAll("button")).find(
    (button) => button.textContent === "Auto-detect",
  ) as HTMLButtonElement;

  await act(async () => {
    detectButton.click();
    await flush();
  });

  assert.equal(calls.length, 1);
  assert.ok(calls[0].includes("/api/weather?"));
  assert.ok(calls[0].includes("range=day"));
  assert.ok(calls[0].includes("city=34.052%2C+-118.244"));
  assert.ok(!calls[0].includes("lat="));
  assert.ok(!calls[0].includes("lon="));

  const deniedGeolocation: Geolocation = {
    clearWatch: () => undefined,
    watchPosition: () => 1,
    getCurrentPosition: (_success, error) => {
      error?.({ code: 1, message: "denied", PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
    },
  };

  Object.defineProperty(globalThis.navigator, "geolocation", {
    configurable: true,
    value: deniedGeolocation,
  });

  await act(async () => {
    detectButton.click();
    await flush();
  });

  assert.ok(document.body.textContent?.includes("Location access was denied"));
});
