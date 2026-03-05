### Prompt 1: Database Layer

Design a PostgreSQL schema (with migrations) for a geolocated weather app. Create tables for users (optional), saved locations, and a weather_cache table keyed by (lat, lon, units, range) with `expires_at` for TTL-based caching. Add indexes for fast lookups by user_id and for fetching the latest non-expired cache entry.

### Prompt 2: Backend Layer

Build a FastAPI backend using the Postgres schema. Integrate OpenWeatherMap (https://openweathermap.org/api) to fetch current weather and forecasts (1 day, 3 days, 7 days), and implement a read-through cache in Postgres to reduce API calls. Add an endpoint to auto-detect approximate user location via `https://ipapi.co/json/`, plus endpoints for saved locations CRUD and for retrieving forecasts by coordinates.

### Prompt 3: Frontend Layer

Build a Svelte frontend that calls the FastAPI backend. Create a simple UI that lets the user type a location or auto-detect it, then displays today, next 3 days, and week forecasts with loading and error states. Include a saved locations dropdown (if available) and unit switching (metric/imperial).
