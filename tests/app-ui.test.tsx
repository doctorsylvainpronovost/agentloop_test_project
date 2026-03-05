import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
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

const waitFor = async (check: () => boolean, attempts = 5): Promise<void> => {
  for (let index = 0; index < attempts; index += 1) {
    if (check()) {
      return;
    }
    await act(async () => {
      await flush();
    });
  }
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

test("renders manual input, geolocation button, ranges, and result region", () => {
  assert.ok(document.querySelector("#location-input"));
  assert.ok(document.querySelector('button[type="button"]'));
  assert.ok(document.querySelector('input[name="forecast-range"][value="day"]'));
  assert.ok(document.querySelector('input[name="forecast-range"][value="three-day"]'));
  assert.ok(document.querySelector('input[name="forecast-range"][value="week"]'));
  assert.ok(document.body.textContent?.includes("Forecast details appear here after a request."));
});

test("shows a validation error when manual location is empty", async () => {
  await submitForm();

  assert.ok(document.body.textContent?.includes("Please enter a location before requesting a forecast."));
});

test("shows loading state and blocks duplicate submit while in flight", async () => {
  let resolveFetch: ((value: Response) => void) | null = null;
  let callCount = 0;

  globalThis.fetch = (async () => {
    callCount += 1;
    return new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Berlin");
  await submitForm();

  const submitButton = document.querySelector('button[type="submit"]') as HTMLButtonElement;
  assert.equal(submitButton.disabled, true);
  assert.equal(locationInput.disabled, false);
  assert.ok(document.body.textContent?.includes("Loading..."));

  await submitForm();
  assert.equal(callCount, 1);

  await act(async () => {
    resolveFetch?.(
      new Response(
        JSON.stringify({
          data: {
            city: "Berlin",
            temperature: 18,
            description: "cloudy",
            units: "metric",
          },
          source: "openweathermap",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await flush();
  });

  assert.ok(document.body.textContent?.includes("Berlin"));
});

test("auto-detect uses coordinates and surfaces geolocation errors", async () => {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(
      JSON.stringify({
        data: {
          city: "Detected City",
          temperature: 17,
          description: "breeze",
          units: "metric",
        },
        source: "openweathermap",
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
  assert.ok(calls[0].includes("range=day"));
  assert.ok(calls[0].includes("lat=34.0522"));
  assert.ok(calls[0].includes("lon=-118.2437"));

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

test("latest request wins when geolocation request follows manual request", async () => {
  const resolvers: Array<(value: Response) => void> = [];
  globalThis.fetch = (async () => {
    return new Promise<Response>((resolve) => {
      resolvers.push(resolve);
    });
  }) as typeof fetch;

  const geolocation: Geolocation = {
    clearWatch: () => undefined,
    watchPosition: () => 1,
    getCurrentPosition: (success) => {
      success({
        coords: {
          latitude: 35.6762,
          longitude: 139.6503,
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
    value: geolocation,
  });

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  const detectButton = Array.from(document.querySelectorAll("button")).find(
    (button) => button.textContent === "Auto-detect",
  ) as HTMLButtonElement;

  await setInputValue(locationInput, "Madrid");

  await act(async () => {
    detectButton.click();
    await flush();
  });

  await submitForm();

  await act(async () => {
    await flush();
  });

  assert.equal(resolvers.length, 2);

  await act(async () => {
    resolvers[0](
      new Response(
        JSON.stringify({
          data: {
            city: "Madrid",
            temperature: 9,
            description: "older",
            units: "metric",
          },
          source: "openweathermap",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await flush();
  });

  await act(async () => {
    resolvers[1](
      new Response(
        JSON.stringify({
          data: {
            city: "Tokyo",
            temperature: 21,
            description: "newer",
            units: "metric",
          },
          source: "openweathermap",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await flush();
  });

  assert.ok(document.body.textContent?.includes("Tokyo"));
  assert.ok(!document.body.textContent?.includes("older"));
});
