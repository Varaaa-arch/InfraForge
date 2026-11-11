import type { AuthTokens } from "@/types/auth";

const ACCESS_TOKEN_KEY = "infraforge.access_token";
const REFRESH_TOKEN_KEY = "infraforge.refresh_token";

export const AUTH_LOGOUT_EVENT = "infraforge:logout";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(tokens: AuthTokens): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function emitAuthLogout(): void {
  window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
}
