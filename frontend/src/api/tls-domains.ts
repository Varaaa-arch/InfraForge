import { apiFetch } from "@/api/client";
import type {
  TlsDomainCreatePayload,
  TlsDomainDetail,
  TlsDomainList,
  TlsDomainStatus,
  TlsDomainUpdatePayload,
} from "@/types/tls-domain";

export interface TlsDomainFilters {
  search?: string;
  status?: TlsDomainStatus;
  enabled?: boolean;
  limit?: number;
  offset?: number;
}

export function fetchTlsDomains(
  filters: TlsDomainFilters = {},
): Promise<TlsDomainList> {
  const params = new URLSearchParams();

  if (filters.search) {
    params.set("search", filters.search);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.enabled !== undefined) {
    params.set("enabled", String(filters.enabled));
  }
  params.set("limit", String(filters.limit ?? 100));
  if (filters.offset) {
    params.set("offset", String(filters.offset));
  }

  return apiFetch<TlsDomainList>(`/tls-domains?${params.toString()}`);
}

export function fetchTlsDomain(domainId: number): Promise<TlsDomainDetail> {
  return apiFetch<TlsDomainDetail>(`/tls-domains/${domainId}`);
}

export function createTlsDomain(
  payload: TlsDomainCreatePayload,
): Promise<TlsDomainDetail> {
  return apiFetch<TlsDomainDetail>("/tls-domains", {
    method: "POST",
    json: payload,
  });
}

export function updateTlsDomain(
  domainId: number,
  payload: TlsDomainUpdatePayload,
): Promise<TlsDomainDetail> {
  return apiFetch<TlsDomainDetail>(`/tls-domains/${domainId}`, {
    method: "PATCH",
    json: payload,
  });
}

export function deleteTlsDomain(domainId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/tls-domains/${domainId}`, {
    method: "DELETE",
  });
}

export function checkTlsDomain(domainId: number): Promise<TlsDomainDetail> {
  return apiFetch<TlsDomainDetail>(`/tls-domains/${domainId}/check`, {
    method: "POST",
  });
}
