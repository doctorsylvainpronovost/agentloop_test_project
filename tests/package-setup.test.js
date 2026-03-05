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
});

test("devDependencies stay minimal for requested frontend setup", async () => {
  const pkg = await loadPackageJson();

  const dependencyKeys = Object.keys(pkg.devDependencies).sort();
  assert.deepEqual(dependencyKeys, ["typescript", "vite"]);
});

test("package.json includes test script recognized by QA", async () => {
  const pkg = await loadPackageJson();

  assert.equal(pkg.scripts.test, "node --test");
});

test("package.json content is valid JSON", async () => {
  const raw = await readFile(packageJsonPath, "utf8");

  assert.doesNotThrow(() => JSON.parse(raw));
});
