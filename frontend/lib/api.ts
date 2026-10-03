import axios, { AxiosError } from "axios";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export const TOKEN_KEY = "aic_access_token";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(
    message: string,
    status: number,
    code = "error",
    details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

// No default Content-Type: axios sets `application/json` for plain objects and
// leaves multipart alone so the browser can append the boundary itself.
export const api = axios.create({
  baseURL: API_URL,
  timeout: 30_000,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const AUTH_PATHS = ["/auth/login", "/auth/register"];

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError = toApiError(error);
    const requestUrl: string =
      (axios.isAxiosError(error) && error.config?.url) || "";
    const isAuthAttempt = AUTH_PATHS.some((path) => requestUrl.includes(path));
    const onLoginPage =
      typeof window !== "undefined" && window.location.pathname === "/login";

    // An expired/invalid session should end the session everywhere.
    if (apiError.status === 401 && !isAuthAttempt && !onLoginPage) {
      clearToken();
      const next = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.assign(`/login?next=${next}`);
    }
    return Promise.reject(error);
  },
);

interface ErrorPayload {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
  code?: string;
}

function flattenValidationDetail(
  detail: ErrorPayload["detail"],
): string | undefined {
  if (!Array.isArray(detail)) return undefined;
  return detail
    .map((item) => {
      const field = item.loc?.slice(1).join(".");
      const message = item.msg ?? "is invalid";
      return field ? `${field}: ${message}` : message;
    })
    .join(", ");
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ErrorPayload>;
    const status = axiosError.response?.status ?? 0;
    const payload = axiosError.response?.data;

    if (payload?.detail && typeof payload.detail === "string") {
      return new ApiError(payload.detail, status, payload.code ?? "error");
    }
    if (payload?.detail) {
      const flat = flattenValidationDetail(payload.detail);
      if (flat) return new ApiError(flat, status, "validation_error");
    }
    if (status === 0) {
      return new ApiError(
        "Cannot reach the server. Is the backend running?",
        0,
        "network_error",
      );
    }
    return new ApiError(
      axiosError.message || "Something went wrong",
      status,
      payload?.code ?? "error",
    );
  }

  if (error instanceof Error) {
    return new ApiError(error.message, 0, "unknown_error");
  }
  return new ApiError("Something went wrong", 0, "unknown_error");
}

export function isUnavailable(error: ApiError): boolean {
  return [404, 501, 502, 503].includes(error.status);
}
