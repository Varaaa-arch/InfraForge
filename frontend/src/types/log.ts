export interface LogEntry {
  timestamp: string;
  timestamp_ns: string;
  line: string;
  level: string | null;
  container: string | null;
  stream: string | null;
}

export interface LogsResponse {
  query: string;
  count: number;
  logs: LogEntry[];
}

export interface LogsContainersResponse {
  count: number;
  containers: string[];
}

export type LogLevel = "all" | "error" | "warning" | "info" | "debug";

export type LogRange = "15m" | "1h" | "6h" | "24h" | "7d";
