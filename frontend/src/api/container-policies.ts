import { apiFetch } from "@/api/client";
import type {
  ContainerIncident,
  ContainerPolicyDetail,
  ContainerPolicyList,
  ContainerPolicyMutationResult,
  ContainerPolicyUpsert,
} from "@/types/container";

export function fetchContainerPolicy(containerId: string): Promise<ContainerPolicyDetail> {
  return apiFetch<ContainerPolicyDetail>(`/containers/${containerId}/policy`);
}

export function saveContainerPolicy(
  containerId: string,
  payload: ContainerPolicyUpsert,
): Promise<ContainerPolicyMutationResult> {
  return apiFetch<ContainerPolicyMutationResult>(`/containers/${containerId}/policy`, {
    method: "PUT",
    json: payload,
  });
}

export function deleteContainerPolicy(
  containerId: string,
  resetLimits = true,
): Promise<{ message: string; container_name: string; reset_limits: boolean }> {
  const params = new URLSearchParams({ reset_limits: String(resetLimits) });
  return apiFetch<{ message: string; container_name: string; reset_limits: boolean }>(
    `/containers/${containerId}/policy?${params.toString()}`,
    { method: "DELETE" },
  );
}

export function fetchContainerPolicies(): Promise<ContainerPolicyList> {
  return apiFetch<ContainerPolicyList>("/container-policies");
}

export function fetchContainerIncidents(
  containerName?: string,
  limit = 50,
): Promise<ContainerIncident[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (containerName) {
    params.set("container_name", containerName);
  }
  return apiFetch<ContainerIncident[]>(`/container-policies/incidents?${params.toString()}`);
}
