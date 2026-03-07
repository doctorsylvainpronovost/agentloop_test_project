# QA Sign-Off: weather_cache Migration and Retrieval Validation

## Environment
- Repository worktree: `task-76`
- Python: `python3`
- Test runner: `pytest`
- Database URL default: `postgresql+psycopg://postgres:postgres@localhost:5432/weather`

## Acceptance Criteria Status
1. **Migrations run clean up/down**: **FAIL (blocked environment)**
   - Repro command:
     - `./scripts/verify_db_migration_and_cache_plan.sh`
   - Observed:
     - `Database verification requires executed integration tests; found 5 skipped test(s).`
   - Expected:
     - No skipped DB integration tests and successful up/down/up revision transitions.

2. **`weather_cache` composite key uniqueness/versioning**: **FAIL (blocked environment)**
   - Repro command:
     - `python3 -m pytest tests/test_migrations.py -k weather_cache_composite_uniqueness_and_versioning -q`
   - Observed:
     - Test skipped because PostgreSQL connection is unavailable.
   - Expected:
     - Duplicate `(latitude, longitude, units, forecast_range, cache_version)` rejected; higher `cache_version` inserts accepted.

3. **Latest non-expired retrieval performant and index-backed**: **FAIL (blocked environment)**
   - Repro commands:
     - `python3 -m pytest tests/test_migrations.py -k latest_non_expired_cache_retrieval_returns_highest_valid_version -q`
     - `python3 -m pytest tests/test_migrations.py -k latest_non_expired_query_plan_prefers_weather_cache_index -q`
   - Observed:
     - Tests skipped because PostgreSQL connection is unavailable.
   - Expected:
     - Retrieval returns latest non-expired record and `EXPLAIN` includes `ix_weather_cache_lookup_latest_non_expired` index scan markers.

4. **Schema docs/comments present and accurate**: **FAIL (blocked environment)**
   - Repro command:
     - `python3 -m pytest tests/test_migrations.py -k weather_cache_schema_documentation_is_present_and_accurate -q`
   - Observed:
     - Test skipped because PostgreSQL connection is unavailable.
   - Expected:
     - PostgreSQL catalog comments exist for `weather_cache` table, `cache_version`, `expires_at`, and the latest lookup index.

## Engineering Bounce Recommendation
- **Severity**: High (release-blocking for DB acceptance validation)
- **Impact**: QA cannot independently validate migration integrity, uniqueness/versioning behavior, query correctness, or index usage.
- **Required actions**:
  1. Provision a reachable PostgreSQL instance matching `DATABASE_URL` in QA environment.
  2. Re-run `./scripts/verify_db_migration_and_cache_plan.sh` to produce execution-backed pass/fail results.
  3. Attach command output plus pytest case IDs for the five DB integration checks.

## Non-DB Verification Completed
- `python3 -m pytest test_migration_tooling.py tests/test_weather_cache_query.py -q` -> pass
- `node --test migration-tooling.test.js` -> pass
