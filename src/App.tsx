import { type FormEvent, useMemo, useRef, useState } from "react";
import {
  fetchForecast,
  formatCoordinateLabel,
  type ForecastResponse,
  getCurrentCoordinates,
  rangeLabels,
  type WeatherRequestErrorKind,
} from "./forecastApi";

const buildManualRequestKey = (location: string): string => {
  return `manual:${location.trim().toLowerCase()}`;
};

const buildGeoRequestKey = (location: string): string => {
  return `geo:${location.toLowerCase()}`;
};

const fallbackMessages: Record<WeatherRequestErrorKind, string> = {
  validation: "Weather request was invalid. Please verify the city name and try again.",
  network: "Network error while fetching weather. Please check your connection and retry.",
  "malformed-payload": "Weather data was malformed. Please try again later.",
  unknown: "Unable to fetch weather right now. Please try again shortly.",
};

const App = (): React.JSX.Element => {
  const [location, setLocation] = useState("");
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeRequestKey, setActiveRequestKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const manualRequestKey = useMemo(() => buildManualRequestKey(location), [location]);

  const runForecastRequest = async (targetLocation: string, requestKey: string): Promise<void> => {
    const thisRequestId = ++requestIdRef.current;
    setLoading(true);
    setActiveRequestKey(requestKey);
    setError(null);

    const response = await fetchForecast({ location: targetLocation });

    if (thisRequestId !== requestIdRef.current) {
      return;
    }

    if (response.ok) {
      setResult(response.data);
    } else {
      setResult(null);
      setError(response.error.message || fallbackMessages[response.error.kind]);
    }

    setLoading(false);
    setActiveRequestKey(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();

    const formData = new window.FormData(event.currentTarget);
    const inputValue = String(formData.get("location") ?? "").trim() || location.trim();

    if (!inputValue) {
      setResult(null);
      setError("Please enter a location before requesting weather.");
      return;
    }

    if (inputValue !== location) {
      setLocation(inputValue);
    }

    const requestKey = buildManualRequestKey(inputValue);
    if (loading && activeRequestKey === requestKey) {
      return;
    }

    await runForecastRequest(inputValue, requestKey);
  };

  const handleDetectLocation = async (): Promise<void> => {
    if (!navigator.geolocation) {
      setResult(null);
      setError("Geolocation is not supported in this browser.");
      return;
    }

    try {
      const coordinates = await getCurrentCoordinates();
      const coordinateLabel = formatCoordinateLabel(coordinates);
      setLocation(coordinateLabel);
      const requestKey = buildGeoRequestKey(coordinateLabel);
      if (loading && activeRequestKey === requestKey) {
        return;
      }
      await runForecastRequest(coordinateLabel, requestKey);
    } catch (geolocationError) {
      const message = geolocationError instanceof Error ? geolocationError.message : "Unable to detect location.";
      setResult(null);
      setError(message);
    }
  };

  const submitDisabled = loading && activeRequestKey === manualRequestKey;
  const detectDisabled = loading && activeRequestKey !== null && activeRequestKey.startsWith("geo:");

  return (
    <main className="weather-shell">
      <section className="card">
        <h1>Weather Forecast</h1>
        <p className="intro">Enter a city or use auto-detect to fetch today's weather.</p>

        <form className="forecast-form" onSubmit={handleSubmit}>
          <label htmlFor="location-input">Location</label>
          <div className="row">
            <input
              id="location-input"
              name="location"
              type="text"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="e.g. Paris"
            />
            <button type="button" onClick={handleDetectLocation} disabled={detectDisabled}>
              Auto-detect
            </button>
          </div>

          <button type="submit" className="submit" disabled={submitDisabled}>
            {loading ? "Loading..." : "Get weather"}
          </button>
        </form>

        <section aria-live="polite" className="status-panel">
          {error ? <p className="error">{error}</p> : null}
          {result ? (
            <article className="result">
              <h2>{rangeLabels.day}</h2>
              <p>
                <strong>Requested for:</strong> {result.locationLabel}
              </p>
              <p>
                <strong>City:</strong> {result.weather.city}
              </p>
              <p>
                <strong>Temperature:</strong> {result.weather.temperature}
              </p>
              <p>
                <strong>Conditions:</strong> {result.weather.description}
              </p>
            </article>
          ) : (
            <p className="hint">Weather details appear here after a request.</p>
          )}
        </section>
      </section>
    </main>
  );
};

export default App;
