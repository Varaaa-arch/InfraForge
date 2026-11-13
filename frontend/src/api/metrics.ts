import { apiFetch } from "@/api/client";
import type { ContainerTrends, MetricsRange } from "@/types/metrics";

export function fetchTopContainers(
  range: MetricsRange,
  limit = 5,
): Promise<ContainerTrends> {
  const params = new URLSearchParams({ range, limit: String(limit) });
  return apiFetch<ContainerTrends>(`/containers/usage/top?${params.toString()}`);
}
