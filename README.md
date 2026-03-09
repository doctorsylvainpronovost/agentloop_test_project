# Weather Web App Scaffold

Minimal full-stack scaffold in repository root:

- Frontend: TypeScript + Vite
- Backend: FastAPI + Uvicorn + httpx

## Install

```bash
npm install
python3 -m pip install -r requirements.txt
```

## Run

Frontend dev server:

```bash
npm run dev
```

Backend dev server:

```bash
export WEATHER_API_KEY=your_weatherapi_key
export WEATHER_BASE_URL=https://api.weatherapi.com/v1
npm run backend:dev
```

## Weather API Contract (Immediate Recovery)

### Canonical endpoint

`GET /api/weather?city=London&range=day`

- Required query parameters:
  - `city`: non-empty string (trimmed)
  - `range`: must be exactly `day`
- Success response `200` (normalized canonical day response):

```json
{
  "data": {
    "city": "London",
    "temperature": 11.5,
    "description": "Partly cloudy"
  }
}
```

This canonical day response is the team contract for day forecasts and should be used by all new integrations.

### Canonical validation and error contract

Error payloads are deterministic and always follow:

```json
{
  "detail": {
    "code": "<stable_machine_code>",
    "message": "<human_readable_message>"
  }
}
```

Acceptance examples:

- Missing `city`

```http
GET /api/weather?range=day
```

```json
{
  "detail": {
    "code": "missing_city",
    "message": "city query parameter is required"
  }
}
```

- Missing `range`

```http
GET /api/weather?city=London
```

```json
{
  "detail": {
    "code": "missing_range",
    "message": "range query parameter is required"
  }
}
```

- Invalid `range`

```http
GET /api/weather?city=London&range=week
```

```json
{
  "detail": {
    "code": "invalid_range",
    "message": "range must be 'day'"
  }
}
```

- Blank `city`

```http
GET /api/weather?city=%20%20%20&range=day
```

```json
{
  "detail": {
    "code": "invalid_city",
    "message": "city must not be empty"
  }
}
```

### Legacy compatibility endpoint and migration

`GET /api/weather/day?location=London` is **deprecated-but-preserved** until the published sunset date. It keeps the legacy payload shape:

```json
{
  "data": {
    "location": {
      "name": "London",
      "region": "City of London, Greater London",
      "country": "United Kingdom",
      "lat": 51.52,
      "lon": -0.11,
      "timezone": "Europe/London"
    },
    "units": "metric",
    "requested_days": 1,
    "forecast": [
      {
        "date": "2026-03-05",
        "temperature": {"min": 5.2, "max": 11.8, "avg": 8.3},
        "condition": {"text": "Partly cloudy", "icon": "//cdn.weatherapi.com/..."},
        "wind_kph": 19.8,
        "humidity": 71,
        "precip_mm": 0.2,
        "chance_of_rain": 35
      }
    ]
  },
  "source": "weatherapi"
}
```

Migration guidance for consumers:

1. Preserve existing location selection logic, but map `location -> city` when calling the canonical endpoint.
2. Replace legacy calls with `GET /api/weather?city=<city>&range=day`.
3. Update day forecast parsing to the canonical day response (`data.city`, `data.temperature`, `data.description`) instead of `data.location` and `data.forecast[0]`.
4. Keep fallback handling for legacy payloads only while supporting older deployed clients.

The legacy endpoint includes deprecation metadata:

- `Deprecation: true`
- `Sunset: Wed, 31 Dec 2026 23:59:59 GMT`
- `Link: </api/weather?city={city}&range=day>; rel="successor-version"`

## Build

```bash
npm run build
```

## Tests

```bash
npm test
```

## SQLite Cache Configuration

The weather API includes a SQLite-based cache to improve performance and reduce external API calls. The cache is automatically managed and requires minimal configuration.

### Environment Variable

- **`WEATHER_CACHE_DB_PATH`** (optional): Path to the SQLite database file
  - Default value: `app.db` (created in the current working directory)
  - Example: `export WEATHER_CACHE_DB_PATH=/var/cache/weather.db`

### Database Schema

The cache uses a `weather_cache` table with the following structure:

```sql
CREATE TABLE IF NOT EXISTS weather_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_key TEXT NOT NULL,
    forecast_range TEXT NOT NULL,
    units TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(city_key, forecast_range, units)
)
```

**Columns:**
- `city_key`: Normalized city name (lowercase, trimmed)
- `forecast_range`: Weather forecast range (`day`, `3day`, `week`)
- `units`: Temperature units (`metric` or `imperial`)
- `status_code`: HTTP status code of cached response (200 for successful responses)
- `payload`: JSON-serialized response payload
- `created_at`: ISO 8601 timestamp when cache entry was created
- `expires_at`: ISO 8601 timestamp when cache entry expires

### Cache Behavior

**Cache Scope:**
- Only the canonical `/api/weather?city=&range=` endpoint uses the cache
- Legacy endpoints (`/api/weather/day`, `/api/weather/3day`, `/api/weather/week`) bypass the cache
- Cache is keyed by: `(city_key, forecast_range, units)`

**Cache Hit/Miss Logic:**
1. On request, the cache is checked for a valid (non-expired) entry
2. **Cache Hit**: Returns cached response immediately (status code 200 only)
3. **Cache Miss**: Fetches from weather API, stores response in cache, then returns

**TTL (Time To Live):**
- Cache entries expire after **900 seconds (15 minutes)**
- Expired entries are automatically ignored on subsequent lookups
- The `expires_at` column determines validity

**Cache Storage:**
- Successful responses (status 200) are cached
- Error responses are not cached
- Uses `INSERT ... ON CONFLICT DO UPDATE` for upsert semantics
- City names are normalized: trimmed and converted to lowercase

### Verifying Cache Operation

**Method 1: Check Database File**
```bash
# Inspect cache entries
sqlite3 app.db "SELECT city_key, forecast_range, units, created_at, expires_at FROM weather_cache;"
```

**Method 2: Monitor Response Headers**
The API doesn't add cache-specific headers, but you can:
1. Make identical requests within 15 minutes
2. Observe faster response times for cached requests
3. Check SQLite database growth

**Method 3: Test Script**
```python
import requests
import time

# First request (cache miss)
start = time.time()
response1 = requests.get("http://localhost:8000/api/weather?city=London&range=day")
time1 = time.time() - start

# Immediate second request (cache hit)
start = time.time()
response2 = requests.get("http://localhost:8000/api/weather?city=London&range=day")
time2 = time.time() - start

print(f"First request: {time1:.3f}s (cache miss)")
print(f"Second request: {time2:.3f}s (cache hit)")
```

### Configuration Examples

**Basic Usage (Default):**
```bash
# Uses default app.db in current directory
npm run backend:dev
```

**Custom Cache Location:**
```bash
export WEATHER_CACHE_DB_PATH=/tmp/weather_cache.db
npm run backend:dev
```

**Disable Cache (Development):**
```bash
# Set to /dev/null or non-writable location
export WEATHER_CACHE_DB_PATH=/dev/null
npm run backend:dev
```

### Migration Notes

The PostgreSQL `weather_cache` table (defined in Alembic migrations) is for future production use with coordinate-based caching. The current SQLite implementation uses a simplified city-based cache for development and testing.

**PostgreSQL Schema (Future):**
```sql
-- Production schema includes coordinates and versioning
CREATE TABLE weather_cache (
    id BIGINT PRIMARY KEY,
    latitude NUMERIC(9,6) NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    units VARCHAR(16) NOT NULL,
    forecast_range VARCHAR(16) NOT NULL,
    cache_version INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE(latitude, longitude, units, forecast_range, cache_version)
);
```
