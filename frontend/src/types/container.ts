export type ContainerStatus =
  | "running"
  | "exited"
  | "created"
  | "paused"
  | "restarting"
  | "removing"
  | "dead"
  | (string & {});

export type ContainerHealth = "healthy" | "unhealthy" | "starting" | (string & {});

export interface ContainerPort {
  container_port: number;
  protocol: string;
  host_port: number | null;
  host_ip: string | null;
}

export interface Container {
  id: string;
  name: string;
  image: string;
  status: ContainerStatus;
  created: string;
  ports: ContainerPort[];
  health: ContainerHealth | null;
  compose_project: string | null;
  compose_service: string | null;
  restart_count: number;
  cpu_percent: number | null;
  memory_usage_bytes: number | null;
  memory_limit_bytes: number | null;
  memory_percent: number | null;
}

export type RestartPolicy = "no" | "always" | "unless-stopped" | "on-failure";

export interface EffectiveContainerLimits {
  cpu_limit_cores: number | null;
  cpu_quota: number | null;
  cpu_period: number | null;
  memory_limit_bytes: number | null;
  restart_policy: string;
}

export interface ContainerPolicy {
  id: number;
  container_name: string;
  container_id: string | null;
  compose_project: string | null;
  compose_service: string | null;
  cpu_limit_cores: number | null;
  cpu_quota: number | null;
  cpu_period: number;
  memory_limit_bytes: number | null;
  restart_policy: RestartPolicy;
  auto_heal_enabled: boolean;
  unhealthy_threshold: number;
  max_restarts: number;
  restart_cooldown_seconds: number;
  unhealthy_streak: number;
  last_health_status: string | null;
  last_restart_at: string | null;
  restart_count_window: number;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContainerPolicyDetail {
  container_id: string;
  container_name: string;
  compose_project: string | null;
  compose_service: string | null;
  status: string;
  health: string | null;
  policy: ContainerPolicy | null;
  effective: EffectiveContainerLimits;
}

export interface ContainerPolicyUpsert {
  cpu_limit_cores?: number | null;
  memory_limit_mib?: number | null;
  restart_policy: RestartPolicy;
  auto_heal_enabled: boolean;
  unhealthy_threshold: number;
  max_restarts: number;
  restart_cooldown_seconds: number;
  apply_now?: boolean;
}

export interface ContainerPolicyMutationResult {
  policy: ContainerPolicy;
  effective: EffectiveContainerLimits;
  message: string;
}

export interface AutoHealWorkerStatus {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  unhealthy_threshold_default: number;
  max_restarts_default: number;
  last_poll_at: string | null;
  last_error: string | null;
  last_stats: Record<string, number> | null;
}

export interface ContainerPolicyList {
  items: ContainerPolicy[];
  worker: AutoHealWorkerStatus;
}

export interface ContainerIncident {
  id: number;
  action: string;
  container_name: string | null;
  created_at: string;
  details: Record<string, unknown> | null;
}
