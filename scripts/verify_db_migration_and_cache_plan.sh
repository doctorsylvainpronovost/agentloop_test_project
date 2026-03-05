#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_FILE="$(mktemp)"
trap 'rm -f "$REPORT_FILE"' EXIT

python3 -m pytest tests/test_migrations.py \
  -k "migration_repeatability_and_revision_integrity or weather_cache_composite_uniqueness_and_versioning or latest_non_expired_cache_retrieval_returns_highest_valid_version or latest_non_expired_query_plan_prefers_weather_cache_index or weather_cache_schema_documentation_is_present_and_accurate" \
  --maxfail=1 \
  --junitxml "$REPORT_FILE" \
  -q "$@"

python3 - "$REPORT_FILE" <<'PYXML'
import sys
import xml.etree.ElementTree as ET

report_file = sys.argv[1]
root = ET.parse(report_file).getroot()
if root.tag == "testsuites":
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in root.findall("testsuite"))
else:
    skipped = int(root.attrib.get("skipped", "0"))

if skipped > 0:
    raise SystemExit(f"Database verification requires executed integration tests; found {skipped} skipped test(s).")
PYXML
