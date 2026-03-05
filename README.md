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

## Weather API Endpoints

- `GET /api/weather/day?location=London` - single-day forecast
- `GET /api/weather/3day?location=London` - 3-day forecast
- `GET /api/weather/week?location=London` - 7-day forecast

All weather endpoints return normalized JSON:

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
    "requested_days": 3,
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

## Build

```bash
npm run build
```

## Tests

```bash
npm test
```
