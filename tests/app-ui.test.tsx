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

test("renders successful forecast response with unchanged summary fields", async () => {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(
      JSON.stringify({
        data: {
          location: { name: "Berlin" },
          units: "metric",
          forecast: [
            {
              date: "2026-03-05",
              temperature: { avg: 18 },
              condition: { text: "Cloudy" },
            },
          ],
        },
        source: "weatherapi",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Berlin");
  await submitForm();

  assert.equal(calls.length, 1);
  assert.equal(calls[0], "http://localhost:8000/api/weather?city=Berlin&range=day");
  assert.ok(document.body.textContent?.includes("Requested for:"));
  assert.ok(document.body.textContent?.includes("Berlin"));
  assert.ok(document.body.textContent?.includes("Temperature:"));
  assert.ok(document.body.textContent?.includes("Cloudy"));
});

test("renders field-level validation message for location errors", async () => {
  globalThis.fetch = (async () => {
    return new Response(
      JSON.stringify({
        detail: [
          {
            loc: ["query", "location"],
            msg: "location must not be empty",
          },
        ],
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Rome");
  await submitForm();

  assert.ok(document.body.textContent?.includes("location must not be empty"));
});

test("renders non-field validation errors for structured 422 payloads", async () => {
  globalThis.fetch = (async () => {
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
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Madrid");
  await submitForm();

  assert.ok(document.body.textContent?.includes("Location is required"));
  assert.ok(document.body.textContent?.includes("Please fix the highlighted fields"));
});

test("falls back to generic validation message when shape is incomplete", async () => {
  globalThis.fetch = (async () => {
    return new Response(JSON.stringify({ detail: {} }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  const locationInput = document.querySelector("#location-input") as HTMLInputElement;
  await setInputValue(locationInput, "Lisbon");
  await submitForm();

  assert.ok(document.body.textContent?.includes("Request validation failed"));
});
