import { apiFetch } from "@/api/client";
import type { Container } from "@/types/container";

export function fetchContainers(all = true): Promise<Container[]> {
  const params = new URLSearchParams({ all: String(all) });
  return apiFetch<Container[]>(`/containers?${params.toString()}`);
}

export function startContainer(containerId: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/containers/${containerId}/start`, {
    method: "POST",
  });
}

export function stopContainer(
  containerId: string,
  timeout = 10,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ timeout: String(timeout) });
  return apiFetch<{ message: string }>(`/containers/${containerId}/stop?${params.toString()}`, {
    method: "POST",
  });
}

export function restartContainer(
  containerId: string,
  timeout = 10,
): Promise<{ message: string }> {
  const params = new URLSearchParams({ timeout: String(timeout) });
  return apiFetch<{ message: string }>(
    `/containers/${containerId}/restart?${params.toString()}`,
    { method: "POST" },
  );
}

export function fetchContainerInspect(
  containerId: string,
): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/containers/${containerId}/inspect`);
}
