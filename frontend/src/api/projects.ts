import { apiFetch } from "@/api/client";
import type {
  Application,
  EnvVarBulkResult,
  EnvVarInput,
  EnvVarList,
  EnvVarMasked,
  EnvVarPlain,
  Project,
} from "@/types/project";

export function fetchProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export function fetchProject(projectId: number): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}`);
}

export function fetchProjectApplications(projectId: number): Promise<Application[]> {
  const params = new URLSearchParams({ project_id: String(projectId) });
  return apiFetch<Application[]>(`/applications?${params.toString()}`);
}

export function fetchEnvVars(projectId: number): Promise<EnvVarList> {
  return apiFetch<EnvVarList>(`/projects/${projectId}/env`);
}

export function bulkUpsertEnvVars(
  projectId: number,
  envVars: EnvVarInput[],
): Promise<EnvVarBulkResult> {
  return apiFetch<EnvVarBulkResult>(`/projects/${projectId}/env`, {
    method: "POST",
    json: { env_vars: envVars },
  });
}

export function updateEnvVar(
  projectId: number,
  envId: number,
  value: string,
): Promise<EnvVarMasked> {
  return apiFetch<EnvVarMasked>(`/projects/${projectId}/env/${envId}`, {
    method: "PATCH",
    json: { value },
  });
}

export function revealEnvVar(projectId: number, envId: number): Promise<EnvVarPlain> {
  return apiFetch<EnvVarPlain>(`/projects/${projectId}/env/${envId}`);
}

export function deleteEnvVar(
  projectId: number,
  envId: number,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/projects/${projectId}/env/${envId}`, {
    method: "DELETE",
  });
}
