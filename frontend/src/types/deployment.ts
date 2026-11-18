export type DeploymentStatus = "pending" | "deploying" | "success" | "failed" | (string & {});

export type TriggerSource = "manual" | "github_webhook" | "ci_token" | (string & {});

export interface Deployment {
  id: number;
  application_id: number;
  server_id: number | null;
  status: DeploymentStatus;
  branch: string;
  trigger_source: TriggerSource;
  commit_sha: string | null;
  log_path: string | null;
  started_at: string;
  finished_at: string | null;
  is_rollback: boolean;
  rollback_of: number | null;
  compose_path_snapshot: string | null;
  duration: number | null;
}

export interface DeploymentQuery {
  projectId?: number;
  applicationId?: number;
  serverId?: number;
  status?: DeploymentStatus;
  limit?: number;
  offset?: number;
}

export interface DeploymentToken {
  id: number;
  project_id: number;
  application_id: number | null;
  name: string;
  prefix: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface DeploymentTokenCreated extends DeploymentToken {
  token: string;
}

export interface DeploymentTokenCreate {
  name: string;
  expires_in_days?: number;
  application_id?: number;
}
