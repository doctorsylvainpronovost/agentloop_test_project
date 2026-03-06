export type ForecastRange = "day";

export type ForecastRequest = {
  location: string;
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
};

export type ForecastResponse = {
  locationLabel: string;
  weather: WeatherPayload;
  source: string;
};

export type WeatherRequestErrorKind = "validation" | "network" | "malformed-payload" | "unknown";

export type WeatherRequestError = {
  kind: WeatherRequestErrorKind;
  message: string;
  statusCode?: number;
};

export type ForecastResult =
  | {
      ok: true;
      data: ForecastResponse;
    }
  | {
      ok: false;
      error: WeatherRequestError;
    };

const PERMISSION_DENIED = 1;
const POSITION_UNAVAILABLE = 2;
const TIMEOUT = 3;

export const rangeLabels: Record<ForecastRange, string> = {
  day: "Today",
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

export const buildForecastRequest = ({ location }: ForecastRequest, options: RequestOptions = {}): string => {
  const normalizedLocation = location.trim();

  if (!normalizedLocation) {
    throw new Error("Please enter a location before requesting weather.");
  }

  const params = new URLSearchParams({ city: normalizedLocation, range: "day" });
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

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === "object" && value !== null;
};

const toWeatherRequestError = (
  kind: WeatherRequestErrorKind,
  fallbackMessage: string,
  statusCode?: number,
  overrideMessage?: string,
): WeatherRequestError => {
  const normalizedMessage = overrideMessage?.trim();

  return {
    kind,
    statusCode,
    message: normalizedMessage || fallbackMessage,
  };
};

const parseValidationMessage = (body: unknown): string | null => {
  if (!isRecord(body)) {
    return null;
  }

  const detail = body.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (isRecord(detail) && typeof detail.message === "string" && detail.message.trim()) {
    return detail.message.trim();
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (isRecord(first) && typeof first.msg === "string" && first.msg.trim()) {
      return first.msg.trim();
    }
  }

  if (typeof body.message === "string" && body.message.trim()) {
    return body.message.trim();
  }

  return null;
};

const parseResponseBody = async (response: Response): Promise<unknown> => {
  try {
    return await response.json();
  } catch {
    return null;
  }
};

const parseForecastBody = (body: unknown): { weather: WeatherPayload; source: string } | null => {
  if (!isRecord(body) || !isRecord(body.data)) {
    return null;
  }

  const city = body.data.city;
  const temperature = body.data.temperature;
  const description = body.data.description;
  const source = typeof body.source === "string" && body.source.trim() ? body.source.trim() : "unknown";

  if (typeof city !== "string" || !city.trim()) {
    return null;
  }

  if (typeof temperature !== "number" || Number.isNaN(temperature)) {
    return null;
  }

  if (typeof description !== "string" || !description.trim()) {
    return null;
  }

  return {
    weather: {
      city: city.trim(),
      temperature,
      description: description.trim(),
    },
    source,
  };
};

export const fetchForecast = async (
  request: ForecastRequest,
  fetchImpl: typeof fetch = fetch,
  options: RequestOptions = {},
): Promise<ForecastResult> => {
  let endpoint: string;
  try {
    endpoint = buildForecastRequest(request, options);
  } catch (error) {
    const message = error instanceof Error ? error.message : undefined;
    return {
      ok: false,
      error: toWeatherRequestError("validation", "Please enter a location before requesting weather.", 422, message),
    };
  }

  let response: Response;
  try {
    response = await fetchImpl(endpoint, { method: "GET" });
  } catch {
    return {
      ok: false,
      error: toWeatherRequestError(
        "network",
        "Network error while fetching weather. Please check your connection and retry.",
      ),
    };
  }

  if (!response.ok) {
    const errorBody = await parseResponseBody(response);

    if (response.status >= 400 && response.status < 500) {
      return {
        ok: false,
        error: toWeatherRequestError(
          "validation",
          "Weather request was invalid. Please verify the city name and try again.",
          response.status,
          parseValidationMessage(errorBody) ?? undefined,
        ),
      };
    }

    return {
      ok: false,
      error: toWeatherRequestError(
        "unknown",
        "Unable to fetch weather right now. Please try again shortly.",
        response.status,
        parseValidationMessage(errorBody) ?? undefined,
      ),
    };
  }

  const body = await parseResponseBody(response);
  const parsed = parseForecastBody(body);

  if (!parsed) {
    return {
      ok: false,
      error: toWeatherRequestError(
        "malformed-payload",
        "Weather data was malformed. Please try again later.",
        response.status,
      ),
    };
  }

  return {
    ok: true,
    data: {
      locationLabel: request.location.trim(),
      weather: parsed.weather,
      source: parsed.source,
    },
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
