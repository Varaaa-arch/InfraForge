import { apiFetch } from "@/api/client";
import type {
  ImageScanDetail,
  ImageScanList,
  ImageScanTriggerPayload,
} from "@/types/image-scan";

export interface ImageScanFilters {
  project_id?: number;
  image?: string;
  limit?: number;
  offset?: number;
}

export function fetchImageScans(
  filters: ImageScanFilters = {},
): Promise<ImageScanList> {
  const params = new URLSearchParams();

  if (filters.project_id !== undefined) {
    params.set("project_id", String(filters.project_id));
  }
  if (filters.image) {
    params.set("image", filters.image);
  }
  params.set("limit", String(filters.limit ?? 100));
  if (filters.offset) {
    params.set("offset", String(filters.offset));
  }

  return apiFetch<ImageScanList>(`/image-scans?${params.toString()}`);
}

export function fetchImageScan(scanId: number): Promise<ImageScanDetail> {
  return apiFetch<ImageScanDetail>(`/image-scans/${scanId}`);
}

export function triggerImageScan(
  payload: ImageScanTriggerPayload,
): Promise<ImageScanDetail> {
  return apiFetch<ImageScanDetail>("/image-scans", {
    method: "POST",
    json: payload,
  });
}

export function rescanImage(scanId: number): Promise<ImageScanDetail> {
  return apiFetch<ImageScanDetail>(`/image-scans/${scanId}/rescan`, {
    method: "POST",
  });
}
