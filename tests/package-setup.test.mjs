import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const currentFile = fileURLToPath(import.meta.url);
const currentDir = dirname(currentFile);
const packageJsonPath = resolve(currentDir, "../package.json");

async function loadPackageJson() {
  const raw = await readFile(packageJsonPath, "utf8");
  return JSON.parse(raw);
}

test("package.json defines required Vite + TypeScript toolchain", async () => {
  const pkg = await loadPackageJson();

  assert.equal(pkg.scripts.build, "vite build");
  assert.equal(pkg.scripts["verify:build"], "npm run build");
  assert.ok(pkg.devDependencies);
  assert.ok(pkg.devDependencies.vite);
  assert.ok(pkg.devDependencies.typescript);
  assert.ok(pkg.devDependencies["@types/node"]);
  assert.ok(pkg.devDependencies.jsdom);
  assert.ok(pkg.dependencies.react);
  assert.ok(pkg.dependencies["react-dom"]);
});

test("frontend test script runs tsx test files before static frontend checks", async () => {
  const pkg = await loadPackageJson();

  assert.match(pkg.scripts["test:frontend"], /^tsx --test .*forecast-api\.test\.ts .*app-ui\.test\.tsx/);
  assert.match(pkg.scripts["test:frontend"], /node --test tests\/frontend-entry\.test\.js tests\/frontend-build\.test\.js/);
});

test("package.json content is valid JSON", async () => {
  const raw = await readFile(packageJsonPath, "utf8");

  assert.doesNotThrow(() => JSON.parse(raw));
});
