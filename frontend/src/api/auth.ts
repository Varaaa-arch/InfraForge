import { apiFetch } from "@/api/client";
import type { AuthTokens, RegisterPayload, User } from "@/types/auth";

export interface LoginPayload {
  username: string;
  password: string;
}

export function loginRequest({ username, password }: LoginPayload): Promise<AuthTokens> {
  return apiFetch<AuthTokens>("/auth/login", {
    method: "POST",
    body: new URLSearchParams({ username, password }),
    skipAuthRefresh: true,
  });
}

export function registerRequest({
  username,
  email,
  password,
}: RegisterPayload): Promise<User> {
  return apiFetch<User>("/auth/register", {
    method: "POST",
    json: { username, email, password },
    skipAuthRefresh: true,
  });
}

export function getCurrentUser(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

export function logoutRequest(refreshToken: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/auth/logout", {
    method: "POST",
    json: { refresh_token: refreshToken },
    skipAuthRefresh: true,
  });
}
