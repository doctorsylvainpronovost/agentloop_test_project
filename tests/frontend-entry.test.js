import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const currentFile = fileURLToPath(import.meta.url);
const currentDir = dirname(currentFile);
const indexHtmlPath = resolve(currentDir, "../index.html");
const mainTsPath = resolve(currentDir, "../src/main.ts");

async function loadFile(path) {
  return readFile(path, "utf8");
}

test("index.html wires Vite entry to /src/main.ts", async () => {
  const html = await loadFile(indexHtmlPath);

  assert.match(html, /<script\s+type="module"\s+src="\/src\/main\.ts"><\/script>/);
});

test("index.html includes app mount element", async () => {
  const html = await loadFile(indexHtmlPath);

  assert.match(html, /<div\s+id="app"><\/div>/);
});

test("main.ts handles missing app element safely", async () => {
  const mainTs = await loadFile(mainTsPath);

  assert.match(mainTs, /if\s*\(app\)\s*\{/);
  assert.match(mainTs, /app\.dataset\.boot\s*=\s*"true"/);
});

test("main.ts sets expected bootstrap text in happy path", async () => {
  const mainTs = await loadFile(mainTsPath);

  assert.match(mainTs, /app\.textContent\s*=\s*"Vite \+ TypeScript frontend is ready\."/);
});
