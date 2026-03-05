const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const rootDir = __dirname;

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
