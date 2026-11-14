import { apiFetch } from "@/api/client";
import type {
  MetricsRange,
  ServerMetrics,
} from "@/types/metrics";
import type {
  Server,
  ServerCreatePayload,
  ServerUpdatePayload,
  SSHTestResult,
} from "@/types/server";

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

export function createServer(payload: ServerCreatePayload): Promise<Server> {
  return apiFetch<Server>("/servers", { method: "POST", json: payload });
}

export function updateServer(
  serverId: number,
  payload: ServerUpdatePayload,
): Promise<Server> {
  return apiFetch<Server>(`/servers/${serverId}`, { method: "PATCH", json: payload });
}

export function deleteServer(serverId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/servers/${serverId}`, { method: "DELETE" });
}

export function testServerConnection(serverId: number): Promise<SSHTestResult> {
  return apiFetch<SSHTestResult>(`/servers/${serverId}/test`, { method: "POST" });
}
