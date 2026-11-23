export type PostureCategory = "image" | "tls" | "container" | (string & {});
export type PostureCheckStatus = "pass" | "warn" | "fail" | "unknown" | (string & {});
export type PostureSeverity = "critical" | "high" | "warning" | "info" | (string & {});
export type PostureLevel = "aman" | "perlu_perhatian" | "berisiko" | (string & {});

export interface ImagePostureSummary {
  total_scans: number;
  completed: number;
  failed: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  affected_images: number;
  latest_scanned_at: string | null;
}

export interface TlsPostureSummary {
  total: number;
  enabled: number;
  healthy: number;
  expiring: number;
  expired: number;
  invalid: number;
  error: number;
  pending: number;
}

export interface ContainerPostureSummary {
  available: boolean;
  total: number;
  running: number;
  privileged: number;
  root_user: number;
  writable_rootfs: number;
  missing_cap_drop_all: number;
  missing_no_new_privileges: number;
  error_message: string | null;
}

export interface PostureCheck {
  key: string;
  category: PostureCategory;
  title: string;
  status: PostureCheckStatus;
  severity: PostureSeverity;
  detail: string;
  count: number;
}

export interface PostureFinding {
  category: PostureCategory;
  severity: PostureSeverity;
  title: string;
  detail: string;
  resource: string | null;
}

export interface SecurityPostureSummary {
  score: number;
  level: PostureLevel;
  generated_at: string;
  images: ImagePostureSummary;
  tls: TlsPostureSummary;
  containers: ContainerPostureSummary;
  checks: PostureCheck[];
  findings: PostureFinding[];
}
