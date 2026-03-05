#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m pytest tests/test_migrations.py -k "upgrade_and_downgrade_round_trip_with_constraint_enforcement or migration_repeatability_and_weather_cache_latest_query_plan" -q "$@"
