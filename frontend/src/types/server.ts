export type ServerStatus = "active" | "inactive" | "error";

export type ServerAuthType = "password" | "private_key";

export type ServerExporterStatus = "not_configured" | "up" | "down" | "unknown";

export interface Server {
  id: number;
  owner_id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  exporter_instance: string | null;
  auth_type: ServerAuthType;
  status: ServerStatus;
  created_at: string;
  updated_at: string;
  exporter_status?: ServerExporterStatus | null;
}

export interface ServerCreatePayload {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: ServerAuthType;
  password?: string | null;
  private_key?: string | null;
  exporter_instance?: string | null;
}

export interface ServerUpdatePayload {
  name?: string;
  host?: string;
  port?: number;
  username?: string;
  auth_type?: ServerAuthType;
  password?: string | null;
  private_key?: string | null;
  exporter_instance?: string | null;
}

export interface SSHTestResult {
  server_id: number;
  host: string;
  port: number;
  success: boolean;
  message: string;
}
