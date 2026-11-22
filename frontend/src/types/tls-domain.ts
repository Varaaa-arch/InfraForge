export type TlsDomainStatus =
  | "pending"
  | "healthy"
  | "expiring"
  | "expired"
  | "invalid"
  | "error"
  | (string & {});

export interface TlsDomainSummary {
  id: number;
  name: string | null;
  host: string;
  port: number;
  enabled: boolean;
  warning_days: number;
  status: TlsDomainStatus;
  days_remaining: number | null;
  expiry_date: string | null;
  issuer: string | null;
  subject: string | null;
  protocol: string | null;
  trusted: boolean;
  error_message: string | null;
  last_checked_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface TlsDomainCheck {
  id: number;
  tls_domain_id: number;
  checked_at: string;
  status: TlsDomainStatus;
  days_remaining: number | null;
  expiry_date: string | null;
  issuer: string | null;
  subject: string | null;
  protocol: string | null;
  trusted: boolean;
  error_message: string | null;
  alert_sent: boolean;
}

export interface TlsDomainDetail extends TlsDomainSummary {
  checks: TlsDomainCheck[];
}

export interface TlsDomainList {
  items: TlsDomainSummary[];
  total: number;
}

export interface TlsDomainCreatePayload {
  name?: string | null;
  host: string;
  port?: number;
  enabled?: boolean;
  warning_days?: number;
  check_now?: boolean;
}

export interface TlsDomainUpdatePayload {
  name?: string | null;
  host?: string;
  port?: number;
  enabled?: boolean;
  warning_days?: number;
}
