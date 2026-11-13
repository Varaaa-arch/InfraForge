import { apiFetch } from "@/api/client";
import type {
  AlertChannel,
  AlertChannelCreatePayload,
  AlertChannelUpdatePayload,
  AlertEvent,
  AlertStatus,
} from "@/types/alert";

export interface AlertFilters {
  status?: AlertStatus;
  severity?: string;
  limit?: number;
  offset?: number;
}

export function fetchAlerts(filters: AlertFilters = {}): Promise<AlertEvent[]> {
  const params = new URLSearchParams();

  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.severity) {
    params.set("severity", filters.severity);
  }
  params.set("limit", String(filters.limit ?? 50));
  if (filters.offset) {
    params.set("offset", String(filters.offset));
  }

  return apiFetch<AlertEvent[]>(`/alerts?${params.toString()}`);
}

export function fetchAlertChannels(): Promise<AlertChannel[]> {
  return apiFetch<AlertChannel[]>("/alert-channels");
}

export function createAlertChannel(
  payload: AlertChannelCreatePayload,
): Promise<AlertChannel> {
  return apiFetch<AlertChannel>("/alert-channels", { method: "POST", json: payload });
}

export function updateAlertChannel(
  channelId: number,
  payload: AlertChannelUpdatePayload,
): Promise<AlertChannel> {
  return apiFetch<AlertChannel>(`/alert-channels/${channelId}`, {
    method: "PATCH",
    json: payload,
  });
}

export function deleteAlertChannel(channelId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/alert-channels/${channelId}`, {
    method: "DELETE",
  });
}

export function testAlertChannel(channelId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/alert-channels/${channelId}/test`, {
    method: "POST",
  });
}
