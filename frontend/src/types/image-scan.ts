export type ImageScanStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | (string & {});

export type VulnerabilitySeverity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "none"
  | "unknown"
  | (string & {});

export interface VulnerabilityFinding {
  cve_id: string;
  package: string;
  installed_version: string | null;
  fixed_version: string | null;
  severity: VulnerabilitySeverity;
  title: string | null;
  target: string | null;
  primary_url: string | null;
}

export interface ImageScanSummary {
  id: number;
  project_id: number | null;
  image_name: string;
  image_digest: string | null;
  status: ImageScanStatus;
  overall_severity: VulnerabilitySeverity | null;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  total_count: number;
  scanner: string;
  error_message: string | null;
  requested_by: string | null;
  scanned_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ImageScanDetail extends ImageScanSummary {
  findings: VulnerabilityFinding[];
}

export interface ImageScanList {
  items: ImageScanSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ImageScanTriggerPayload {
  image_name: string;
  project_id?: number | null;
}
