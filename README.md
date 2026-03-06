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
- Success response `200`:

```json
{
  "data": {
    "city": "London",
    "temperature": 11.5,
    "description": "Partly cloudy"
  }
}
```

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

### Legacy compatibility endpoint

`GET /api/weather/day?location=London` is preserved for backward compatibility and keeps its legacy payload shape:

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

The legacy endpoint now includes explicit deprecation metadata:

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
