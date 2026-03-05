import { test } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(new URL("..", import.meta.url).pathname);

test("npm run build generates frontend dist output", () => {
  execSync("npm run build", { cwd: ROOT, stdio: "pipe" });
  assert.equal(existsSync(resolve(ROOT, "dist/index.html")), true);
});
