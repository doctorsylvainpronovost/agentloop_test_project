import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

test('required frontend scaffold files exist', () => {
  const requiredFiles = [
    'package.json',
    path.join('src', 'main.ts'),
    'index.html',
    path.join('backend', 'main.py'),
    'requirements.txt',
  ];

  for (const file of requiredFiles) {
    assert.equal(fs.existsSync(path.join(rootDir, file)), true, `${file} should exist`);
  }
});

test('package.json defines non-watch production build script', () => {
  const packagePath = path.join(rootDir, 'package.json');
  const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'));

  assert.equal(typeof packageJson.scripts?.build, 'string');
  assert.match(packageJson.scripts.build, /vite\s+build/);
});
