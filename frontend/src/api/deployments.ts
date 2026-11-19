import { apiFetch } from "@/api/client";
import type { Deployment, DeploymentQuery } from "@/types/deployment";

export function fetchDeployments(query: DeploymentQuery = {}): Promise<Deployment[]> {
  const params = new URLSearchParams();
  if (query.projectId !== undefined) {
    params.set("project_id", String(query.projectId));
  }
  if (query.applicationId !== undefined) {
    params.set("application_id", String(query.applicationId));
  }
  if (query.serverId !== undefined) {
    params.set("server_id", String(query.serverId));
  }
  if (query.status !== undefined) {
    params.set("status", query.status);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  if (query.offset !== undefined) {
    params.set("offset", String(query.offset));
  }

  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return apiFetch<Deployment[]>(`/deployments${suffix}`);
}

export function rollbackDeployment(deploymentId: number): Promise<Deployment> {
  return apiFetch<Deployment>(`/deployments/${deploymentId}/rollback`, {
    method: "POST",
  });
}
