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
