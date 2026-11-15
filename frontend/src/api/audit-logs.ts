import { apiFetch } from "@/api/client";
import type {
  AuditFilterMeta,
  AuditLogList,
  AuditLogQuery,
} from "@/types/audit-log";

export function fetchAuditLogs(query: AuditLogQuery = {}): Promise<AuditLogList> {
  const params = new URLSearchParams();

  if (query.username) {
    params.set("username", query.username);
  }
  if (query.action) {
    params.set("action", query.action);
  }
  if (query.from) {
    params.set("from", query.from);
  }
  if (query.to) {
    params.set("to", query.to);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  if (query.offset !== undefined) {
    params.set("offset", String(query.offset));
  }

  const search = params.toString();
  return apiFetch<AuditLogList>(`/audit-logs${search ? `?${search}` : ""}`);
}

export function fetchAuditFilterMeta(): Promise<AuditFilterMeta> {
  return apiFetch<AuditFilterMeta>("/audit-logs/filters");
}
