export type ForecastRange = "day" | "three-day" | "week";

export type ForecastRequest = {
  location: string;
  range: ForecastRange;
  coordinates?: { lat: number; lon: number };
};

export const CANONICAL_DAY_ENDPOINT = "/api/weather";
export const CANONICAL_DAY_QUERY_GUIDANCE = "Use city and range=day query parameters for canonical day forecasts.";
export const CANONICAL_DAY_RESPONSE_SCHEMA_GUIDANCE =
  "Canonical day responses normalize data to { data: { city: string, temperature: number, description: string } }.";
export const LEGACY_DAY_ENDPOINT = "/api/weather/day";
export const LEGACY_DAY_MIGRATION_GUIDANCE =
  "Legacy /api/weather/day?location=... remains available but is deprecated. Migrate by mapping location -> city and calling /api/weather?city=<city>&range=day.";

export type LegacyContractNotice = {
  endpoint: typeof LEGACY_DAY_ENDPOINT;
  status: "deprecated-but-preserved";
  locationParam: "location";
  canonicalCityParam: "city";
  canonicalRangeValue: "day";
  migration: string;
};

export const legacyDayContractNotice: LegacyContractNotice = {
  endpoint: LEGACY_DAY_ENDPOINT,
  status: "deprecated-but-preserved",
  locationParam: "location",
  canonicalCityParam: "city",
  canonicalRangeValue: "day",
  migration: LEGACY_DAY_MIGRATION_GUIDANCE,
};

type RequestOptions = {
  apiBaseUrl?: string;
};

type FrontendEnv = {
  VITE_API_BASE_URL?: string;
  VITE_BACKEND_URL?: string;
  VITE_BACKEND_BASE_URL?: string;
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

type ErrorDetail = {
  code?: string;
  message?: string;
};

type ErrorBody = {
  detail?: string | ErrorDetail;
};

type CanonicalWeatherBody = {
  city: string;
  temperature: number;
  description: string;
};

type LegacyWeatherDay = {
  temperature?: {
    avg?: number;
  };
  condition?: {
    text?: string;
  };
};

type LegacyWeatherBody = {
  location: {
    name: string;
  };
  units?: string;
  forecast: LegacyWeatherDay[];
};

type ForecastBody = {
  data?: CanonicalWeatherBody | LegacyWeatherBody;
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

const readFrontendEnv = (): FrontendEnv => {
  const importMeta = import.meta as ImportMeta & {
    env?: FrontendEnv;
  };

  return importMeta.env ?? {};
};

export const resolveApiBaseUrl = (configuredBaseUrl?: string, env: FrontendEnv = readFrontendEnv()): string => {
  const normalizedConfigured = configuredBaseUrl?.trim() ?? "";
  const normalizedPrimary = env.VITE_API_BASE_URL?.trim() ?? "";
  const normalizedCompatibility = env.VITE_BACKEND_URL?.trim() || env.VITE_BACKEND_BASE_URL?.trim() || "";
  const value = normalizedConfigured || normalizedPrimary || normalizedCompatibility || DEFAULT_API_BASE_URL;

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

  const baseUrl = resolveApiBaseUrl(options.apiBaseUrl);

  if (range === "day") {
    const params = new URLSearchParams({ city: normalizedLocation, range });

    if (coordinates) {
      params.set("lat", String(coordinates.lat));
      params.set("lon", String(coordinates.lon));
    }

    return `${baseUrl}${CANONICAL_DAY_ENDPOINT}?${params.toString()}`;
  }

  const legacyPath = range === "three-day" ? "/api/weather/3day" : "/api/weather/week";
  const params = new URLSearchParams({ location: normalizedLocation, units: "metric" });
  return `${baseUrl}${legacyPath}?${params.toString()}`;
};

const isCanonicalWeatherBody = (data: ForecastBody["data"]): data is CanonicalWeatherBody => {
  return !!data && typeof (data as CanonicalWeatherBody).city === "string" && typeof (data as CanonicalWeatherBody).temperature === "number" && typeof (data as CanonicalWeatherBody).description === "string";
};

const isLegacyWeatherBody = (data: ForecastBody["data"]): data is LegacyWeatherBody => {
  return !!data && typeof (data as LegacyWeatherBody).location?.name === "string" && Array.isArray((data as LegacyWeatherBody).forecast);
};

const toForecastResponse = (request: ForecastRequest, body: ForecastBody): ForecastResponse => {
  if (isCanonicalWeatherBody(body.data)) {
    return {
      locationLabel: request.location,
      range: request.range,
      weather: {
        city: body.data.city,
        temperature: body.data.temperature,
        description: body.data.description,
        units: "metric",
      },
      source: body.source ?? "weatherapi",
    };
  }

  if (isLegacyWeatherBody(body.data)) {
    const firstDay = body.data.forecast[0];
    const temperature = firstDay?.temperature?.avg;
    const description = firstDay?.condition?.text;

    if (typeof temperature === "number" && typeof description === "string" && description.length > 0) {
      return {
        locationLabel: request.location,
        range: request.range,
        weather: {
          city: body.data.location.name,
          temperature,
          description,
          units: body.data.units ?? "metric",
        },
        source: body.source ?? "weatherapi",
      };
    }
  }

  throw new Error("Received malformed forecast data.");
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
      if (typeof errorBody.detail === "string") {
        detail = errorBody.detail;
      } else if (errorBody.detail?.message) {
        detail = errorBody.detail.message;
      }
    } catch {
      // ignore parsing errors and fallback to default detail
    }

    throw new Error(detail);
  }

  const body = (await response.json()) as ForecastBody;
  return toForecastResponse(request, body);
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
