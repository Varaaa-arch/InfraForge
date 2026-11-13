export interface DashboardSummary {
  projects: number;
  applications: number;
  deployments: number;
  servers: number;
  servers_active: number;
  servers_inactive: number;
  servers_error: number;
  containers: number;
  containers_total: number;
  alerts_active: number;
  alerts_critical: number;
  alerts_warning: number;
  alerts_info: number;
  generated_at: string;
}
