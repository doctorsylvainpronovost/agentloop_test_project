import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

test('requirements.txt remains intentionally empty', () => {
  const requirementsPath = path.join(rootDir, 'requirements.txt');
  const content = fs.readFileSync(requirementsPath, 'utf8');
  assert.equal(content, '');
});

test('backend/main.py executes successfully', () => {
  const scriptPath = path.join(rootDir, 'backend', 'main.py');
  const result = spawnSync('python3', [scriptPath], { encoding: 'utf8' });

  assert.equal(result.status, 0);
  assert.equal(result.stderr, '');
  assert.match(result.stdout, /Backend scaffold is running\.\n/);
});
