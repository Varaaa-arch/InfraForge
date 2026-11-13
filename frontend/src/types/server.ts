export type ServerStatus = "active" | "inactive" | "error";

export type ServerAuthType = "password" | "private_key";

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
}
