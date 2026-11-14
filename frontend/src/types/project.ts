export type ProjectVisibility = "private" | "public";

export type GitProvider = "github" | "gitlab" | "bitbucket" | (string & {});

export type AppStatus =
  | "idle"
  | "deploying"
  | "running"
  | "failed"
  | (string & {});

export interface Project {
  id: number;
  owner_id: number;
  name: string;
  slug: string;
  description: string | null;
  visibility: ProjectVisibility;
  repository_url: string | null;
  default_branch: string | null;
  provider: GitProvider | null;
  repository_connected_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Application {
  id: number;
  project_id: number;
  name: string;
  repository: string | null;
  branch: string;
  dockerfile_path: string;
  compose_path: string;
  build_context: string | null;
  status: AppStatus;
  created_at: string;
  updated_at: string;
}

export interface EnvVarMasked {
  id: number;
  project_id: number;
  key: string;
  masked_value: string;
  pending_redeploy: boolean;
  created_at: string;
  updated_at: string;
}

export interface EnvVarPlain {
  id: number;
  project_id: number;
  key: string;
  value: string;
  created_at: string;
  updated_at: string;
}

export interface EnvVarList {
  env_vars: EnvVarMasked[];
  last_deployment_at: string | null;
}

export interface EnvVarInput {
  key: string;
  value: string;
}

export interface EnvVarBulkSummary {
  created: number;
  updated: number;
  total: number;
}

export interface EnvVarBulkResult {
  summary: EnvVarBulkSummary;
  env_vars: EnvVarPlain[];
}
