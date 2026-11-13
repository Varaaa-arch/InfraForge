import { apiFetch } from "@/api/client";
import type { MetricsRange, ServerMetrics } from "@/types/metrics";
import type { Server } from "@/types/server";

export function fetchServers(): Promise<Server[]> {
  return apiFetch<Server[]>("/servers");
}

export function fetchServerMetrics(
  serverId: number,
  range: MetricsRange,
): Promise<ServerMetrics> {
  const params = new URLSearchParams({ range });
  return apiFetch<ServerMetrics>(`/servers/${serverId}/metrics?${params.toString()}`);
}
