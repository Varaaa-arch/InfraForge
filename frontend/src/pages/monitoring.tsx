import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Activity, RefreshCw, ServerOff, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { fetchServerMetrics, fetchServers } from "@/api/servers";
import {
  MetricChart,
  type ChartPoint,
  type ChartSeriesConfig,
} from "@/components/monitoring/metric-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { MetricSeries, MetricsRange, ServerMetricKey } from "@/types/metrics";

const ranges: { value: MetricsRange; label: string }[] = [
  { value: "15m", label: "15 menit" },
  { value: "1h", label: "1 jam" },
  { value: "6h", label: "6 jam" },
  { value: "24h", label: "24 jam" },
];

const cpuSeries: ChartSeriesConfig[] = [
  { key: "cpu_percent", label: "CPU", color: "var(--chart-1)" },
];

const memorySeries: ChartSeriesConfig[] = [
  { key: "memory_percent", label: "RAM", color: "var(--chart-2)" },
];

const diskSeries: ChartSeriesConfig[] = [
  { key: "disk_usage_percent", label: "Pemakaian", color: "var(--chart-3)" },
  { key: "disk_io_percent", label: "I/O time", color: "var(--chart-4)" },
];

const networkSeries: ChartSeriesConfig[] = [
  { key: "network_rx_bytes", label: "RX", color: "var(--chart-5)" },
  { key: "network_tx_bytes", label: "TX", color: "var(--chart-1)" },
];

function mergeSeries(
  series: Partial<Record<ServerMetricKey, MetricSeries>>,
  keys: ServerMetricKey[],
): ChartPoint[] {
  const points = new Map<number, ChartPoint>();

  for (const key of keys) {
    for (const point of series[key]?.points ?? []) {
      const timestamp = new Date(point.timestamp).getTime();
      const entry = points.get(timestamp) ?? { timestamp };
      entry[key] = point.value;
      points.set(timestamp, entry);
    }
  }

  return [...points.values()].sort((a, b) => a.timestamp - b.timestamp);
}

export function MonitoringPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const rangeParam = searchParams.get("range");
  const range = ranges.some((item) => item.value === rangeParam)
    ? (rangeParam as MetricsRange)
    : "1h";
  const serverParam = Number(searchParams.get("server"));

  const serversQuery = useQuery({
    queryKey: ["servers"],
    queryFn: fetchServers,
    refetchInterval: 30_000,
    retry: 1,
  });

  const exporterServers = useMemo(
    () => (serversQuery.data ?? []).filter((server) => server.exporter_instance),
    [serversQuery.data],
  );
  const selectedServer =
    exporterServers.find((server) => server.id === serverParam) ?? exporterServers[0] ?? null;
  const selectedId = selectedServer?.id ?? null;

  const metricsQuery = useQuery({
    queryKey: ["server-metrics", selectedId, range],
    queryFn: () => fetchServerMetrics(selectedId as number, range),
    enabled: selectedId !== null,
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
    retry: 1,
  });

  const metrics = metricsQuery.data;

  const cpuData = useMemo(
    () => mergeSeries(metrics?.series ?? {}, ["cpu_percent"]),
    [metrics],
  );
  const memoryData = useMemo(
    () => mergeSeries(metrics?.series ?? {}, ["memory_percent"]),
    [metrics],
  );
  const diskData = useMemo(
    () => mergeSeries(metrics?.series ?? {}, ["disk_usage_percent", "disk_io_percent"]),
    [metrics],
  );
  const networkData = useMemo(
    () => mergeSeries(metrics?.series ?? {}, ["network_rx_bytes", "network_tx_bytes"]),
    [metrics],
  );

  const metricsError = metricsQuery.error
    ? metricsQuery.error instanceof ApiError
      ? metricsQuery.error.message
      : "Tidak dapat memuat metrik server."
    : null;

  function updateParam(key: string, value: string) {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  const noExporter = !serversQuery.isPending && !serversQuery.isError && exporterServers.length === 0;
  const chartsLoading = metricsQuery.isPending && selectedId !== null;

  return (
    <div className="space-y-6" data-testid="monitoring">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Monitoring</h1>
          <p className="text-sm text-muted-foreground">
            Grafik CPU, memori, disk, dan jaringan dari Prometheus (node-exporter).
          </p>
        </div>
        <Badge
          variant="outline"
          className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
        >
          <span className="relative flex size-1.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
            <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500" />
          </span>
          Auto-refresh 30 detik
        </Badge>
      </div>

      <Card size="sm">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <Select
            value={selectedId === null ? "" : String(selectedId)}
            onValueChange={(value) => updateParam("server", value)}
            disabled={serversQuery.isPending || exporterServers.length === 0}
          >
            <SelectTrigger className="w-[220px]" aria-label="Pilih server">
              <SelectValue placeholder="Pilih server" />
            </SelectTrigger>
            <SelectContent>
              {exporterServers.map((server) => (
                <SelectItem key={server.id} value={String(server.id)}>
                  {server.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={range} onValueChange={(value) => updateParam("range", value)}>
            <SelectTrigger className="w-[150px]" aria-label="Rentang waktu">
              <SelectValue placeholder="Rentang" />
            </SelectTrigger>
            <SelectContent>
              {ranges.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button
            variant="outline"
            size="sm"
            onClick={() => void metricsQuery.refetch()}
            disabled={metricsQuery.isFetching || selectedId === null}
          >
            <RefreshCw className={cn("size-3.5", metricsQuery.isFetching && "animate-spin")} />
            Muat ulang
          </Button>

          {selectedServer ? (
            <span className="ml-auto flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-mono">
                {selectedServer.host}:{selectedServer.port}
              </span>
              <span>· exporter {selectedServer.exporter_instance}</span>
              {metrics ? <span>· step {metrics.step_seconds}s</span> : null}
            </span>
          ) : null}
        </CardContent>
      </Card>

      {serversQuery.isPending ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-[310px] w-full rounded-xl" />
          ))}
        </div>
      ) : serversQuery.isError ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">
              {serversQuery.error instanceof ApiError
                ? serversQuery.error.message
                : "Tidak dapat memuat daftar server."}
            </p>
            <Button variant="outline" size="sm" onClick={() => void serversQuery.refetch()}>
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : noExporter ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <ServerOff className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada server dengan exporter</p>
            <p className="max-w-md text-xs text-muted-foreground">
              Isi kolom <code className="font-mono">exporter_instance</code> pada server (mis.{" "}
              <code className="font-mono">host.docker.internal:9100</code>) agar metrik Prometheus
              dapat ditampilkan.
            </p>
          </CardContent>
        </Card>
      ) : metricsError ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{metricsError}</p>
            <Button variant="outline" size="sm" onClick={() => void metricsQuery.refetch()}>
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : chartsLoading ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-[310px] w-full rounded-xl" />
          ))}
        </div>
      ) : metrics && !metrics.available ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <Activity className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Metrik belum tersedia</p>
            <p className="max-w-md text-xs text-muted-foreground">
              {metrics.message ??
                "Prometheus tidak dapat dihubungi atau target node-exporter sedang tidak aktif."}
            </p>
            <Button variant="outline" size="sm" onClick={() => void metricsQuery.refetch()}>
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <MetricChart
            title="CPU usage"
            description={`Persentase pemakaian CPU host · ${metrics?.server_name ?? ""}`}
            data={cpuData}
            series={cpuSeries}
            unit="percent"
          />
          <MetricChart
            title="Memory usage"
            description="Persentase RAM terpakai dibanding total."
            data={memoryData}
            series={memorySeries}
            unit="percent"
          />
          <MetricChart
            title="Disk"
            description="Pemakaian filesystem dan waktu I/O disk."
            data={diskData}
            series={diskSeries}
            unit="percent"
            variant="line"
          />
          <MetricChart
            title="Network"
            description="Throughput jaringan masuk (RX) dan keluar (TX)."
            data={networkData}
            series={networkSeries}
            unit="bytes_per_second"
            variant="line"
          />
        </div>
      )}

      {metrics ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Detail polling</CardTitle>
            <CardDescription>
              Data diambil dari Prometheus range query dengan step {metrics.step_seconds} detik.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
            <span>
              Server: <span className="text-foreground">{metrics.server_name}</span>
            </span>
            <span>
              Instance: <span className="font-mono text-foreground">{metrics.exporter_instance ?? "—"}</span>
            </span>
            <span>
              Rentang: <span className="text-foreground">{metrics.range}</span>
            </span>
            <span>
              Diperbarui:{" "}
              <span className="text-foreground">
                {new Intl.DateTimeFormat("id-ID", {
                  dateStyle: "medium",
                  timeStyle: "medium",
                }).format(new Date(metrics.generated_at))}
              </span>
            </span>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
