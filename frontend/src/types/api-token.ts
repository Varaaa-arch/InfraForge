export type ApiTokenScope = "read" | "write";

export interface ApiToken {
  id: number;
  name: string;
  prefix: string;
  scopes: ApiTokenScope[] | null;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiTokenCreated extends ApiToken {
  token: string;
}

export interface CreateApiTokenInput {
  name: string;
  scopes?: ApiTokenScope[];
  expires_in_days?: number;
}
