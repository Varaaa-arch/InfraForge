import { apiFetch } from "@/api/client";
import type { LogLevel, LogRange, LogsContainersResponse, LogsResponse } from "@/types/log";

export interface LogFilters {
  container?: string;
  level?: LogLevel;
  q?: string;
  last?: LogRange;
  limit?: number;
}

export function fetchLogs(filters: LogFilters = {}): Promise<LogsResponse> {
  const params = new URLSearchParams();

  if (filters.q) {
    params.set("q", filters.q);
  }
  if (filters.container && filters.container !== "all") {
    params.set("container", filters.container);
  }
  if (filters.level && filters.level !== "all") {
    params.set("level", filters.level);
  }
  params.set("last", filters.last ?? "1h");
  params.set("limit", String(filters.limit ?? 500));

  return apiFetch<LogsResponse>(`/logs?${params.toString()}`);
}

export function fetchLogContainers(): Promise<LogsContainersResponse> {
  return apiFetch<LogsContainersResponse>("/logs/containers");
}
