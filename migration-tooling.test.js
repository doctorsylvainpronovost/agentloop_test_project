const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const ROOT = __dirname;
const DEFAULT_DATABASE_URL = 'postgresql+psycopg://postgres:postgres@localhost:5432/weather';

function runWithPythonModule(moduleName, args) {
  const pythonCommands = ['python3', 'python'];

  for (const python of pythonCommands) {
    const result = spawnSync(python, ['-m', moduleName, ...args], {
      cwd: ROOT,
      env: {
        ...process.env,
        DATABASE_URL: process.env.DATABASE_URL || DEFAULT_DATABASE_URL,
      },
      encoding: 'utf8',
    });

    if (result.error) {
      if (result.error.code === 'ENOENT') {
        continue;
      }
      return result;
    }

    return result;
  }

  return {
    status: 1,
    stdout: '',
    stderr: 'Python runtime was not found (tried: python3, python).',
  };
}

test('migration tooling is configured for PostgreSQL and baseline revision exists', () => {
  const requirementsPath = path.join(ROOT, 'requirements.txt');
  const alembicIniPath = path.join(ROOT, 'alembic.ini');
  const baselineRevisionPath = path.join(ROOT, 'alembic', 'versions', '0001_baseline.py');

  assert.equal(fs.existsSync(requirementsPath), true);
  assert.equal(fs.existsSync(alembicIniPath), true);
  assert.equal(fs.existsSync(baselineRevisionPath), true);

  const requirements = fs.readFileSync(requirementsPath, 'utf8');
  assert.match(requirements, /alembic/);
  assert.match(requirements, /sqlalchemy/);
  assert.match(requirements, /psycopg\[binary\]/);

  const alembicIni = fs.readFileSync(alembicIniPath, 'utf8');
  assert.match(alembicIni, /sqlalchemy\.url\s*=\s*postgresql\+psycopg:\/\//);
});

test('alembic can discover and render the deterministic revision chain', () => {
  const heads = runWithPythonModule('alembic', ['-c', 'alembic.ini', 'heads']);
  assert.equal(heads.status, 0, heads.stderr || 'alembic heads failed');
  assert.match(heads.stdout, /0001_baseline/);

  const upgradeSql = runWithPythonModule('alembic', ['-c', 'alembic.ini', 'upgrade', 'head', '--sql']);
  assert.equal(upgradeSql.status, 0, upgradeSql.stderr || 'alembic upgrade --sql failed');
  assert.match(upgradeSql.stdout, /0001_baseline/);
});
