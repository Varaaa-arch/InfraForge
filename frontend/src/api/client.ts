import {
  clearTokens,
  emitAuthLogout,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/auth-storage";
import { isTokenExpiring } from "@/lib/jwt";
import type { ApiErrorBody, ApiResponse, ValidationErrorItem } from "@/types/api";
import type { AuthTokens } from "@/types/auth";

const configuredApiUrl = import.meta.env.VITE_API_URL as string | undefined;

export const API_BASE_URL =
  configuredApiUrl === undefined
    ? "http://localhost:8000"
    : configuredApiUrl.trim().replace(/\/+$/, "");

function resolveWebSocketBaseUrl(base: string): string {
  if (base.startsWith("http://") || base.startsWith("https://")) {
    return base.replace(/^http/, "ws");
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const path = base.startsWith("/") ? base : `/${base}`;
  return `${protocol}//${window.location.host}${base ? path : ""}`;
}

export const WS_BASE_URL = resolveWebSocketBaseUrl(API_BASE_URL);

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | null;
  json?: unknown;
  skipAuthRefresh?: boolean;
}

function isValidationErrorItem(value: unknown): value is ValidationErrorItem {
  return (
    typeof value === "object" &&
    value !== null &&
    "msg" in value &&
    typeof (value as ValidationErrorItem).msg === "string"
  );
}

function extractErrorMessage(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "Terjadi kesalahan yang tidak diketahui.";
  }

  const body = payload as ApiErrorBody;
  if (typeof body.detail === "string") {
    return body.detail;
  }
  if (Array.isArray(body.detail)) {
    const messages = body.detail.filter(isValidationErrorItem).map((item) => item.msg);
    if (messages.length > 0) {
      return messages.join(", ");
    }
  }
  if (typeof body.message === "string") {
    return body.message;
  }
  return "Terjadi kesalahan yang tidak diketahui.";
}

async function refreshSession(): Promise<AuthTokens | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      return null;
    }

    const payload = (await response.json()) as ApiResponse<AuthTokens>;
    setTokens(payload.data);
    return payload.data;
  } catch {
    return null;
  }
}

let refreshInFlight: Promise<AuthTokens | null> | null = null;

function refreshOnce(): Promise<AuthTokens | null> {
  if (!refreshInFlight) {
    refreshInFlight = refreshSession().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function send(
  path: string,
  options: ApiRequestOptions,
  accessToken: string | null,
): Promise<Response> {
  const { json, skipAuthRefresh, body: rawBody, headers: rawHeaders, ...rest } = options;
  void skipAuthRefresh;

  const headers = new Headers(rawHeaders);
  let body = rawBody;

  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  return fetch(`${API_BASE_URL}${path}`, { ...rest, headers, body });
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let payload: unknown = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, extractErrorMessage(payload), payload);
  }

  if (typeof payload === "object" && payload !== null && "data" in payload) {
    return (payload as ApiResponse<T>).data;
  }
  return payload as T;
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { skipAuthRefresh = false } = options;
  let response = await send(path, options, getAccessToken());

  if (response.status === 401 && !skipAuthRefresh && getRefreshToken()) {
    const refreshed = await refreshOnce();
    if (refreshed) {
      response = await send(path, options, refreshed.access_token);
    }
  }

  if (response.status === 401) {
    clearTokens();
    emitAuthLogout();
  }

  return parseResponse<T>(response);
}

export async function ensureValidAccessToken(): Promise<string | null> {
  const token = getAccessToken();

  if (token && !isTokenExpiring(token)) {
    return token;
  }

  const refreshed = await refreshOnce();
  if (refreshed) {
    return refreshed.access_token;
  }

  if (token && !isTokenExpiring(token, 0)) {
    return token;
  }

  return null;
}
