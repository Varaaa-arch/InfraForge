import { Activity, Container, TriangleAlert } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ContainerTrend, ContainerTrends } from "@/types/metrics";

interface TopContainersProps {
  data?: ContainerTrends;
  loading?: boolean;
  error?: string | null;
}

const byteFormatter = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 });

function formatBytes(value: number): string {
  if (value >= 1024 * 1024 * 1024) {
    return `${byteFormatter.format(value / (1024 * 1024 * 1024))} GB`;
  }
  if (value >= 1024 * 1024) {
    return `${byteFormatter.format(value / (1024 * 1024))} MB`;
  }
  if (value >= 1024) {
    return `${byteFormatter.format(value / 1024)} KB`;
  }
  return `${Math.round(value)} B`;
}

function percentage(value: number, maximum: number): number {
  if (maximum <= 0) {
    return 0;
  }
  return Math.min(100, Math.max(0, (value / maximum) * 100));
}

function CpuSparkline({ container }: { container: ContainerTrend }) {
  const points = container.cpu_points.map((point) => ({
    timestamp: new Date(point.timestamp).getTime(),
    value: point.value,
  }));

  if (points.length < 2) {
    return (
      <div className="flex h-10 w-[120px] items-center justify-center rounded-md bg-muted/40 text-[10px] text-muted-foreground">
        tren belum tersedia
      </div>
    );
  }

  return (
    <div className="h-10 w-[120px]" data-testid="top-container-sparkline">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <YAxis hide domain={[0, "auto"]} />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--chart-1)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface UsageBarProps {
  label: string;
  value: string;
  percent: number;
  color: string;
  testId: string;
}

function UsageBar({ label, value, percent, color, testId }: UsageBarProps) {
  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex items-baseline justify-between gap-2 text-[11px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${percent}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function ContainerRow({
  container,
  maxCpu,
  maxMemory,
}: {
  container: ContainerTrend;
  maxCpu: number;
  maxMemory: number;
}) {
  return (
    <div
      className="grid items-center gap-3 rounded-lg border bg-card/50 p-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_120px]"
      data-testid="top-container-row"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{container.name}</span>
          {container.service ? (
            <Badge variant="secondary" className="shrink-0 text-[10px]">
              {container.service}
            </Badge>
          ) : null}
        </div>
        <p className="truncate font-mono text-[11px] text-muted-foreground">
          {container.image ?? container.compose_project ?? "—"}
        </p>
      </div>

      <UsageBar
        label="CPU"
        value={`${container.cpu_percent.toFixed(1)}%`}
        percent={percentage(container.cpu_percent, maxCpu)}
        color="var(--chart-1)"
        testId="top-container-cpu"
      />
      <UsageBar
        label="RAM"
        value={formatBytes(container.memory_bytes)}
        percent={percentage(container.memory_bytes, maxMemory)}
        color="var(--chart-2)"
        testId="top-container-memory"
      />

      <div className="flex justify-end">
        <CpuSparkline container={container} />
      </div>
    </div>
  );
}

export function TopContainers({ data, loading = false, error = null }: TopContainersProps) {
  const containers = data?.containers ?? [];
  const maxCpu = Math.max(1, ...containers.map((container) => container.cpu_percent));
  const maxMemory = Math.max(1, ...containers.map((container) => container.memory_bytes));

  return (
    <Card data-testid="top-containers">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Container className="size-4 text-muted-foreground" />
              Top container
            </CardTitle>
            <CardDescription>
              Lima container dengan CPU tertinggi beserta pemakaian RAM dan tren CPU
              5 menit terakhir (exporter backend → Prometheus).
            </CardDescription>
          </div>
          <Badge variant="outline" className="gap-1.5">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            Auto-refresh 30 detik
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2, 3, 4].map((index) => (
              <Skeleton key={index} className="h-[74px] w-full rounded-lg" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
          </div>
        ) : containers.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Activity className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada data container</p>
            <p className="max-w-md text-xs text-muted-foreground">
              {data?.message ??
                "Exporter backend belum mengirim metrik container atau Prometheus belum melakukan scrape."}
            </p>
          </div>
        ) : (
          containers.map((container) => (
            <ContainerRow
              key={container.name}
              container={container}
              maxCpu={maxCpu}
              maxMemory={maxMemory}
            />
          ))
        )}
      </CardContent>
    </Card>
  );
}
