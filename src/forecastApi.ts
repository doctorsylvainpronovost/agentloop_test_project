export type ForecastRange = "day" | "three-day" | "week";

export type ForecastRequest = {
  location: string;
  range: ForecastRange;
  coordinates?: { lat: number; lon: number };
};

type RequestOptions = {
  apiBaseUrl?: string;
};

export type WeatherPayload = {
  city: string;
  temperature: number;
  description: string;
  units: string;
};

export type ForecastResponse = {
  locationLabel: string;
  range: ForecastRange;
  weather: WeatherPayload;
  source: string;
};

type ErrorBody = {
  detail?: string;
};

type ForecastBody = {
  data?: WeatherPayload;
  source?: string;
};

const PERMISSION_DENIED = 1;
const POSITION_UNAVAILABLE = 2;
const TIMEOUT = 3;

export const rangeLabels: Record<ForecastRange, string> = {
  day: "Today",
  "three-day": "Next 3 Days",
  week: "Full Week",
};

const DEFAULT_API_BASE_URL = "http://localhost:8000";

const readFrontendEnv = (): { VITE_API_BASE_URL?: string } => {
  const importMeta = import.meta as ImportMeta & {
    env?: {
      VITE_API_BASE_URL?: string;
    };
  };

  return importMeta.env ?? {};
};

export const resolveApiBaseUrl = (configuredBaseUrl = readFrontendEnv().VITE_API_BASE_URL): string => {
  const normalized = configuredBaseUrl?.trim() ?? "";
  const value = normalized || DEFAULT_API_BASE_URL;

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(value);
  } catch {
    throw new Error("VITE_API_BASE_URL must be an absolute URL (for example: http://localhost:8000).");
  }

  return parsedUrl.toString().replace(/\/$/, "");
};

export const buildForecastRequest = (
  { location, range, coordinates }: ForecastRequest,
  options: RequestOptions = {},
): string => {
  const normalizedLocation = location.trim();

  if (!normalizedLocation) {
    throw new Error("Please enter a location before requesting a forecast.");
  }

  const params = new URLSearchParams({ city: normalizedLocation, range });

  if (coordinates) {
    params.set("lat", String(coordinates.lat));
    params.set("lon", String(coordinates.lon));
  }

  const baseUrl = resolveApiBaseUrl(options.apiBaseUrl);

  return `${baseUrl}/api/weather?${params.toString()}`;
};

const describeGeolocationError = (error: GeolocationPositionError): string => {
  if (error.code === PERMISSION_DENIED) {
    return "Location access was denied. Please enter a city manually.";
  }

  if (error.code === TIMEOUT) {
    return "Location lookup timed out. Please try again or enter a city manually.";
  }

  if (error.code === POSITION_UNAVAILABLE) {
    return "Current location is unavailable. Please enter a city manually.";
  }

  return "Location detection failed. Please enter a city manually.";
};

export const fetchForecast = async (
  request: ForecastRequest,
  fetchImpl: typeof fetch = fetch,
  options: RequestOptions = {},
): Promise<ForecastResponse> => {
  const endpoint = buildForecastRequest(request, options);
  const response = await fetchImpl(endpoint);

  if (!response.ok) {
    let detail = "Unable to fetch forecast.";

    try {
      const errorBody = (await response.json()) as ErrorBody;
      if (errorBody.detail) {
        detail = errorBody.detail;
      }
    } catch {
      // ignore parsing errors and fallback to default detail
    }

    throw new Error(detail);
  }

  const body = (await response.json()) as ForecastBody;

  if (!body.data?.city || typeof body.data.temperature !== "number" || !body.data.description) {
    throw new Error("Received malformed forecast data.");
  }

  return {
    locationLabel: request.location,
    range: request.range,
    weather: body.data,
    source: body.source ?? "unknown",
  };
};

export const getCurrentCoordinates = (
  geolocation: Geolocation = navigator.geolocation,
): Promise<{ lat: number; lon: number }> => {
  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        });
      },
      (error) => {
        reject(new Error(describeGeolocationError(error)));
      },
      {
        enableHighAccuracy: false,
        timeout: 10000,
      },
    );
  });
};

export const formatCoordinateLabel = ({ lat, lon }: { lat: number; lon: number }): string => {
  return `${lat.toFixed(3)}, ${lon.toFixed(3)}`;
};
