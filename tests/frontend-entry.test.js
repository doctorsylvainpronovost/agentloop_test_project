import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const currentFile = fileURLToPath(import.meta.url);
const currentDir = dirname(currentFile);
const indexHtmlPath = resolve(currentDir, "../index.html");
const mainTsxPath = resolve(currentDir, "../src/main.tsx");

async function loadFile(path) {
  return readFile(path, "utf8");
}

test("index.html wires Vite entry to frontend entry point", async () => {
  const html = await loadFile(indexHtmlPath);

  assert.match(html, /<script\s+type="module"\s+src="\/src\/main\.(ts|tsx)"><\/script>/);
});

test("index.html includes app mount element", async () => {
  const html = await loadFile(indexHtmlPath);

  assert.match(html, /<(main|div)\s+id="app"><\/(main|div)>/);
});

test("main entry mounts app safely", async () => {
  const mainEntry = await loadFile(mainTsxPath);

  assert.match(mainEntry, /createRoot|querySelector.*#app/);
});
