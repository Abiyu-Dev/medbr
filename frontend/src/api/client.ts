import type { ApiError, Tokens } from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "/api/v1";
const ACCESS_KEY = "mb_access";
const REFRESH_KEY = "mb_refresh";
const TIMEOUT_MS = 30000;

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens(tokens: Tokens) {
  localStorage.setItem(ACCESS_KEY, tokens.access);
  localStorage.setItem(REFRESH_KEY, tokens.refresh);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

function handleUnauthorized() {
  clearTokens();
  if (onUnauthorized) onUnauthorized();
  else window.location.assign("/login");
}

// Single shared refresh promise so concurrent 401s trigger only one refresh.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const res = await fetch(`${BASE_URL}/auth/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as Tokens;
    setTokens(data);
    return data.access;
  } catch {
    return null;
  }
}

function normalizeError(status: number, body: unknown): ApiError {
  if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;
    if (typeof obj.detail === "string") {
      return { status, detail: obj.detail, code: obj.code as string | undefined };
    }
    // DRF field-keyed validation errors
    const fieldErrors: Record<string, string[]> = {};
    let first = "";
    for (const [key, value] of Object.entries(obj)) {
      if (Array.isArray(value)) {
        const msgs = value.map(String);
        fieldErrors[key] = msgs;
        if (!first) first = msgs[0];
      } else if (typeof value === "string") {
        fieldErrors[key] = [value];
        if (!first) first = value;
      }
    }
    if (Object.keys(fieldErrors).length) {
      return { status, detail: first || "Please correct the errors below.", fieldErrors };
    }
  }
  const fallback: Record<number, string> = {
    400: "The request could not be processed.",
    403: "You do not have permission to perform this action.",
    404: "This record does not exist or is no longer available.",
    409: "This action conflicts with the current state. Refresh and try again.",
    429: "Too many requests. Please wait a moment and try again.",
    500: "The server encountered an unexpected error.",
  };
  return { status, detail: fallback[status] || `Request failed (${status}).` };
}

interface RequestOptions {
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  auth?: boolean;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function rawRequest(
  method: string,
  path: string,
  opts: RequestOptions,
  token: string | null,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const external = opts.signal;
  const onAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener("abort", onAbort);
  }
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (token && opts.auth !== false) headers["Authorization"] = `Bearer ${token}`;
  try {
    return await fetch(buildUrl(path, opts.params), {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
    if (external) external.removeEventListener("abort", onAbort);
  }
}

export async function request<T>(
  method: string,
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const isAuthPath = path.startsWith("/auth/token");
  let token = getAccessToken();
  let res: Response;
  try {
    res = await rawRequest(method, path, opts, token);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw { status: 0, detail: "The request timed out. Check your connection and retry." } as ApiError;
    }
    throw { status: 0, detail: "Network error. Could not reach the server." } as ApiError;
  }

  // Attempt a single token refresh on 401 for authenticated, non-auth endpoints.
  if (res.status === 401 && !isAuthPath && opts.auth !== false && getRefreshToken()) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }
    const newToken = await refreshPromise;
    if (newToken) {
      token = newToken;
      try {
        res = await rawRequest(method, path, opts, token);
      } catch {
        throw { status: 0, detail: "Network error during retry. Please try again." } as ApiError;
      }
    } else {
      handleUnauthorized();
      throw { status: 401, detail: "Your session has expired. Please sign in again." } as ApiError;
    }
  }

  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!res.ok) {
    if (res.status === 401 && !isAuthPath) handleUnauthorized();
    throw normalizeError(res.status, body);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"], signal?: AbortSignal) =>
    request<T>("GET", path, { params, signal }),
  post: <T>(path: string, body?: unknown, params?: RequestOptions["params"]) =>
    request<T>("POST", path, { body, params }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

export function isApiError(err: unknown): err is ApiError {
  return typeof err === "object" && err !== null && "status" in err && "detail" in err;
}

export function errorMessage(err: unknown): string {
  if (isApiError(err)) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}