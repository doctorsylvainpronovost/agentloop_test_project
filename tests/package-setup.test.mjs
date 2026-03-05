import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const currentFile = fileURLToPath(import.meta.url);
const currentDir = dirname(currentFile);
const packageJsonPath = resolve(currentDir, "../package.json");

test("package.json defines required Vite + TypeScript toolchain", async () => {
  const raw = await readFile(packageJsonPath, "utf8");
  const pkg = JSON.parse(raw);

  assert.equal(pkg.scripts.build, "vite build");
  assert.equal(pkg.scripts["verify:build"], "npm run build");
  assert.ok(pkg.devDependencies);
  assert.ok(pkg.devDependencies.vite);
  assert.ok(pkg.devDependencies.typescript);
});
