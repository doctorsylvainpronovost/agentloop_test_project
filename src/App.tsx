import { type FormEvent, useMemo, useRef, useState } from "react";
import {
  fetchForecast,
  ForecastApiError,
  formatCoordinateLabel,
  type ForecastRange,
  type ForecastResponse,
  getCurrentCoordinates,
  rangeLabels,
  type ValidationErrors,
} from "./forecastApi";

const ranges: ForecastRange[] = ["day", "three-day", "week"];

const buildManualRequestKey = (location: string, range: ForecastRange): string => {
  return `manual:${location.trim().toLowerCase()}|${range}`;
};

const buildGeoRequestKey = (location: string, range: ForecastRange): string => {
  return `geo:${location.toLowerCase()}|${range}`;
};

const App = (): React.JSX.Element => {
  const [location, setLocation] = useState("");
  const [selectedRange, setSelectedRange] = useState<ForecastRange>("day");
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeRequestKey, setActiveRequestKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<ValidationErrors | null>(null);
  const requestIdRef = useRef(0);

  const manualRequestKey = useMemo(() => buildManualRequestKey(location, selectedRange), [location, selectedRange]);

  const runForecastRequest = async (
    targetLocation: string,
    range: ForecastRange,
    requestKey: string,
    coordinates?: { lat: number; lon: number },
  ): Promise<void> => {
    const thisRequestId = ++requestIdRef.current;
    setLoading(true);
    setActiveRequestKey(requestKey);
    setError(null);
    setValidationErrors(null);

    try {
      const data = await fetchForecast({ location: targetLocation, range, coordinates });
      if (thisRequestId !== requestIdRef.current) {
        return;
      }
      setResult(data);
      setValidationErrors(null);
    } catch (requestError) {
      if (thisRequestId !== requestIdRef.current) {
        return;
      }

      const message = requestError instanceof Error ? requestError.message : "Something went wrong.";
      setResult(null);
      setError(message);
      if (requestError instanceof ForecastApiError) {
        setValidationErrors(requestError.validationErrors);
      }
    } finally {
      if (thisRequestId === requestIdRef.current) {
        setLoading(false);
        setActiveRequestKey(null);
      }
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();

    const formData = new window.FormData(event.currentTarget);
    const inputValue = String(formData.get("location") ?? "").trim() || location.trim();

    if (!inputValue) {
      setResult(null);
      setValidationErrors(null);
      setError("Please enter a location before requesting a forecast.");
      return;
    }

    if (inputValue !== location) {
      setLocation(inputValue);
    }

    const requestKey = buildManualRequestKey(inputValue, selectedRange);
    if (loading && activeRequestKey === requestKey) {
      return;
    }

    await runForecastRequest(inputValue, selectedRange, requestKey);
  };

  const handleDetectLocation = async (): Promise<void> => {
    if (!navigator.geolocation) {
      setResult(null);
      setValidationErrors(null);
      setError("Geolocation is not supported in this browser.");
      return;
    }

    try {
      const coordinates = await getCurrentCoordinates();
      const coordinateLabel = formatCoordinateLabel(coordinates);
      setLocation(coordinateLabel);
      const requestKey = buildGeoRequestKey(coordinateLabel, selectedRange);
      if (loading && activeRequestKey === requestKey) {
        return;
      }
      await runForecastRequest(coordinateLabel, selectedRange, requestKey, coordinates);
    } catch (geolocationError) {
      const message = geolocationError instanceof Error ? geolocationError.message : "Unable to detect location.";
      setResult(null);
      setValidationErrors(null);
      setError(message);
    }
  };

  const submitDisabled = loading && activeRequestKey === manualRequestKey;
  const detectDisabled = loading && activeRequestKey !== null && activeRequestKey.startsWith("geo:");
  const locationErrors = validationErrors?.fieldErrors.location ?? [];
  const generalErrors = validationErrors?.generalErrors ?? [];

  return (
    <main className="weather-shell">
      <section className="card">
        <h1>Weather Forecast</h1>
        <p className="intro">Enter a city or use auto-detect, then choose a forecast window.</p>

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

          {locationErrors.length > 0 ? <p className="error">{locationErrors[0]}</p> : null}

          <fieldset className="range-options">
            <legend>Forecast range</legend>
            <div className="range-grid">
              {ranges.map((range) => (
                <label key={range}>
                  <input
                    type="radio"
                    name="forecast-range"
                    value={range}
                    checked={selectedRange === range}
                    onChange={() => setSelectedRange(range)}
                  />
                  {rangeLabels[range]}
                </label>
              ))}
            </div>
          </fieldset>

          <button type="submit" className="submit" disabled={submitDisabled}>
            {loading ? "Loading..." : "Get forecast"}
          </button>
        </form>

        <section aria-live="polite" className="status-panel">
          {generalErrors.length > 0 ? (
            <ul className="error" aria-label="validation errors">
              {generalErrors.map((message, index) => (
                <li key={`${message}-${index}`}>{message}</li>
              ))}
            </ul>
          ) : null}
          {generalErrors.length === 0 && error ? <p className="error">{error}</p> : null}
          {result ? (
            <article className="result">
              <h2>{rangeLabels[result.range]}</h2>
              <p>
                <strong>Requested for:</strong> {result.locationLabel}
              </p>
              <p>
                <strong>City:</strong> {result.weather.city}
              </p>
              <p>
                <strong>Temperature:</strong> {result.weather.temperature} {result.weather.units === "metric" ? "C" : "F"}
              </p>
              <p>
                <strong>Conditions:</strong> {result.weather.description}
              </p>
            </article>
          ) : (
            <p className="hint">Forecast details appear here after a request.</p>
          )}
        </section>
      </section>
    </main>
  );
};

export default App;
