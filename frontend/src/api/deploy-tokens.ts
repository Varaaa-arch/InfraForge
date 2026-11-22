import { apiFetch } from "@/api/client";
import type {
  DeploymentToken,
  DeploymentTokenCreate,
  DeploymentTokenCreated,
} from "@/types/deployment";

export function fetchDeployTokens(projectId: number): Promise<DeploymentToken[]> {
  return apiFetch<DeploymentToken[]>(`/projects/${projectId}/deploy-tokens`);
}

export function createDeployToken(
  projectId: number,
  payload: DeploymentTokenCreate,
): Promise<DeploymentTokenCreated> {
  return apiFetch<DeploymentTokenCreated>(`/projects/${projectId}/deploy-tokens`, {
    method: "POST",
    json: payload,
  });
}

export function rotateDeployToken(
  projectId: number,
  tokenId: number,
  expiresInDays?: number,
): Promise<DeploymentTokenCreated> {
  return apiFetch<DeploymentTokenCreated>(
    `/projects/${projectId}/deploy-tokens/${tokenId}/rotate`,
    {
      method: "POST",
      json: expiresInDays ? { expires_in_days: expiresInDays } : {},
    },
  );
}

export function revokeDeployToken(
  projectId: number,
  tokenId: number,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(
    `/projects/${projectId}/deploy-tokens/${tokenId}`,
    { method: "DELETE" },
  );
}
