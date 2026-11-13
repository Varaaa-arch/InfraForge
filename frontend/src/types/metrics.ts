export interface MetricPoint {
  timestamp: string;
  value: number;
}

export interface MetricSummary {
  current: number;
  average: number;
  maximum: number;
  minimum: number;
}

export interface MetricSeries {
  unit: string;
  points: MetricPoint[];
  summary: MetricSummary | null;
}

export type ServerMetricKey =
  | "cpu_percent"
  | "memory_percent"
  | "disk_usage_percent"
  | "disk_io_percent"
  | "network_rx_bytes"
  | "network_tx_bytes";

export type MetricsRange = "15m" | "1h" | "6h" | "24h";

export interface ServerMetrics {
  server_id: number;
  server_name: string;
  exporter_instance: string | null;
  range: string;
  step_seconds: number;
  available: boolean;
  message: string | null;
  generated_at: string;
  series: Partial<Record<ServerMetricKey, MetricSeries>>;
}

export interface ContainerTrend {
  name: string;
  service: string | null;
  compose_project: string | null;
  image: string | null;
  cpu_percent: number;
  memory_bytes: number;
  cpu_points: MetricPoint[];
}

export interface ContainerTrends {
  range: string;
  step_seconds: number;
  available: boolean;
  message: string | null;
  generated_at: string;
  containers: ContainerTrend[];
}
