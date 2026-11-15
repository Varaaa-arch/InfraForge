export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  method: string;
  path: string;
  resource_type: string | null;
  resource_id: string | null;
  status_code: number;
  ip_address: string | null;
  user_agent: string | null;
  details: Record<string, string> | null;
  created_at: string;
}

export interface AuditLogList {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFilterMeta {
  actions: string[];
  usernames: string[];
  is_admin: boolean;
}

export interface AuditLogQuery {
  username?: string;
  action?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}
