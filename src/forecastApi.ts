export type ForecastRange = "day" | "three-day" | "week";

export type ForecastRequest = {
  location: string;
  range: ForecastRange;
  coordinates?: { lat: number; lon: number };
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

export type ValidationErrors = {
  fieldErrors: Record<string, string[]>;
  generalErrors: string[];
};

type LegacyForecastData = {
  city?: unknown;
  temperature?: unknown;
  description?: unknown;
  units?: unknown;
};

type ForecastBody = {
  data?: unknown;
  source?: unknown;
};

type FastApiValidationIssue = {
  loc?: unknown;
  msg?: unknown;
  message?: unknown;
};

const PERMISSION_DENIED = 1;
const POSITION_UNAVAILABLE = 2;
const TIMEOUT = 3;
const DEFAULT_API_BASE_URL = "http://localhost:8000";

const RANGE_ENDPOINT: Record<ForecastRange, string> = {
  day: "day",
  "three-day": "3day",
  week: "week",
};

export const rangeLabels: Record<ForecastRange, string> = {
  day: "Today",
  "three-day": "Next 3 Days",
  week: "Full Week",
};

export class ForecastApiError extends Error {
  readonly status: number;

  readonly validationErrors: ValidationErrors | null;

  constructor(message: string, status: number, validationErrors: ValidationErrors | null = null) {
    super(message);
    this.name = "ForecastApiError";
    this.status = status;
    this.validationErrors = validationErrors;
  }
}

const readFrontendEnv = (): FrontendEnv => {
  const importMeta = import.meta as ImportMeta & {
    env?: FrontendEnv;
  };

  return importMeta.env ?? {};
};

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === "object" && value !== null;
};

const asText = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

const asNumber = (value: unknown): number | null => {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

const parseFastApiValidationIssues = (detail: unknown): ValidationErrors => {
  const fieldErrors: Record<string, string[]> = {};
  const generalErrors: string[] = [];

  if (typeof detail === "string") {
    return { fieldErrors, generalErrors: [detail] };
  }

  if (Array.isArray(detail)) {
    for (const issue of detail) {
      const typedIssue = isRecord(issue) ? (issue as FastApiValidationIssue) : null;
      const message = asText(typedIssue?.msg) ?? asText(typedIssue?.message);

      if (!message) {
        continue;
      }

      const location = Array.isArray(typedIssue?.loc) ? typedIssue.loc : [];
      const segments = location.map((segment) => (typeof segment === "string" ? segment : null)).filter(Boolean) as string[];
      const field = segments.length > 1 && ["query", "path", "body", "header", "cookie"].includes(segments[0])
        ? segments[1]
        : segments[segments.length - 1];

      if (field && field !== "__root__") {
        if (!fieldErrors[field]) {
          fieldErrors[field] = [];
        }
        fieldErrors[field].push(message);
        continue;
      }

      generalErrors.push(message);
    }

    return { fieldErrors, generalErrors };
  }

  if (!isRecord(detail)) {
    return { fieldErrors, generalErrors };
  }

  const nestedErrors = isRecord(detail.errors) ? detail.errors : null;
  if (nestedErrors) {
    for (const [field, messages] of Object.entries(nestedErrors)) {
      if (Array.isArray(messages)) {
        const normalized = messages.map(asText).filter((item): item is string => item !== null);
        if (normalized.length > 0) {
          fieldErrors[field] = normalized;
        }
      } else {
        const singleMessage = asText(messages);
        if (singleMessage) {
          fieldErrors[field] = [singleMessage];
        }
      }
    }
  }

  const topLevelMessage = asText(detail.message);
  if (topLevelMessage) {
    generalErrors.push(topLevelMessage);
  }

  const nonFieldErrors = detail.non_field_errors;
  if (Array.isArray(nonFieldErrors)) {
    for (const message of nonFieldErrors) {
      const normalized = asText(message);
      if (normalized) {
        generalErrors.push(normalized);
      }
    }
  }

  return { fieldErrors, generalErrors };
};

const toValidationError = (body: unknown): ValidationErrors => {
  if (!isRecord(body)) {
    return {
      fieldErrors: {},
      generalErrors: ["Request validation failed. Please review your input and try again."],
    };
  }

  const detail = body.detail;
  const parsed = parseFastApiValidationIssues(detail);
  const hasFieldErrors = Object.keys(parsed.fieldErrors).length > 0;

  if (hasFieldErrors || parsed.generalErrors.length > 0) {
    return parsed;
  }

  const fallback = asText(body.message) ?? asText(body.error);
  return {
    fieldErrors: {},
    generalErrors: [fallback ?? "Request validation failed. Please review your input and try again."],
  };
};

const parseFailure = (status: number, body: unknown): ForecastApiError => {
  if (status === 422) {
    const validationErrors = toValidationError(body);
    const message = validationErrors.generalErrors[0] ?? "Request validation failed.";
    return new ForecastApiError(message, status, validationErrors);
  }

  if (isRecord(body)) {
    const detail = body.detail;

    if (typeof detail === "string") {
      return new ForecastApiError(detail, status);
    }

    if (isRecord(detail)) {
      const message = asText(detail.message);
      if (message) {
        return new ForecastApiError(message, status);
      }
    }

    const message = asText(body.message);
    if (message) {
      return new ForecastApiError(message, status);
    }
  }

  return new ForecastApiError("Unable to fetch forecast.", status);
};

const parseLegacyWeather = (data: unknown): WeatherPayload | null => {
  const body = isRecord(data) ? (data as LegacyForecastData) : null;
  if (!body) {
    return null;
  }

  const city = asText(body.city);
  const description = asText(body.description);
  const temperature = asNumber(body.temperature);
  const units = asText(body.units) ?? "metric";

  if (!city || !description || temperature === null) {
    return null;
  }

  return {
    city,
    description,
    temperature,
    units,
  };
};

const parseNormalizedWeather = (data: unknown): WeatherPayload | null => {
  if (!isRecord(data)) {
    return null;
  }

  const location = isRecord(data.location) ? data.location : null;
  const city = asText(location?.name);
  const forecast = Array.isArray(data.forecast) ? data.forecast : null;
  const firstDay = forecast && forecast.length > 0 && isRecord(forecast[0]) ? forecast[0] : null;
  const temperatures = isRecord(firstDay?.temperature) ? firstDay.temperature : null;
  const condition = isRecord(firstDay?.condition) ? firstDay.condition : null;

  const temperature = asNumber(temperatures?.avg) ?? asNumber(temperatures?.max) ?? asNumber(temperatures?.min);
  const description = asText(condition?.text);
  const units = asText(data.units) ?? "metric";

  if (!city || !description || temperature === null) {
    return null;
  }

  return {
    city,
    description,
    temperature,
    units,
  };
};

const parseSuccessBody = (body: ForecastBody): { weather: WeatherPayload; source: string } => {
  const weather = parseNormalizedWeather(body.data) ?? parseLegacyWeather(body.data);
  if (!weather) {
    throw new Error("Received malformed forecast data.");
  }

  return {
    weather,
    source: asText(body.source) ?? "unknown",
  };
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

  const params = new URLSearchParams({
    city: normalizedLocation,
    range: range === "three-day" ? "3day" : range,
    units: "metric",
  });

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
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    throw parseFailure(response.status, body);
  }

  const body = (await response.json()) as ForecastBody;
  const parsed = parseSuccessBody(body);

  return {
    locationLabel: request.location,
    range: request.range,
    weather: parsed.weather,
    source: parsed.source,
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
