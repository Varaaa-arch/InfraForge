import { apiFetch } from "@/api/client";
import type {
  ApiToken,
  ApiTokenCreated,
  CreateApiTokenInput,
} from "@/types/api-token";

export function fetchApiTokens(): Promise<ApiToken[]> {
  return apiFetch<ApiToken[]>("/api-tokens");
}

export function createApiToken(input: CreateApiTokenInput): Promise<ApiTokenCreated> {
  return apiFetch<ApiTokenCreated>("/api-tokens", {
    method: "POST",
    json: input,
  });
}

export function revokeApiToken(tokenId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api-tokens/${tokenId}`, {
    method: "DELETE",
  });
}
