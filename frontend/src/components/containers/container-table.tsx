import { Loader2Icon, Play, RotateCw, ScanSearch, Square } from "lucide-react";

import { UsageBar } from "@/components/containers/usage-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Container } from "@/types/container";

const statusStyles: Record<string, { label: string; className: string }> = {
  running: {
    label: "Running",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  paused: {
    label: "Paused",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  restarting: {
    label: "Restarting",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  exited: {
    label: "Exited",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
  created: {
    label: "Created",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
  dead: {
    label: "Dead",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

const healthStyles: Record<string, { label: string; className: string }> = {
  healthy: {
    label: "Healthy",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  unhealthy: {
    label: "Unhealthy",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  starting: {
    label: "Starting",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
};

function formatBytes(value: number): string {
  if (value >= 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  }
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(0)} MB`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(0)} KB`;
  }
  return `${Math.round(value)} B`;
}

interface ContainerTableProps {
  containers: Container[];
  busyContainerId?: string | null;
  onStart: (container: Container) => void;
  onStop: (container: Container) => void;
  onRestart: (container: Container) => void;
  onInspect: (container: Container) => void;
}

export function ContainerTable({
  containers,
  busyContainerId = null,
  onStart,
  onStop,
  onRestart,
  onInspect,
}: ContainerTableProps) {
  const maxCpu = Math.max(1, ...containers.map((item) => item.cpu_percent ?? 0));

  return (
    <div className="overflow-x-auto">
      <Table data-testid="container-table">
        <TableHeader>
          <TableRow>
            <TableHead>Nama</TableHead>
            <TableHead>Image</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Health</TableHead>
            <TableHead>Ports</TableHead>
            <TableHead className="text-right">Restart</TableHead>
            <TableHead className="min-w-[110px]">CPU</TableHead>
            <TableHead className="min-w-[120px]">RAM</TableHead>
            <TableHead className="text-right">Aksi</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {containers.map((container) => {
            const status = statusStyles[container.status] ?? {
              label: container.status,
              className:
                "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
            };
            const health = container.health ? healthStyles[container.health] : null;
            const busy = busyContainerId === container.id;
            const isRunning = container.status === "running";
            const cpuPercent = container.cpu_percent ?? 0;
            const memoryPercent = container.memory_percent ?? 0;

            return (
              <TableRow key={container.id} data-testid="container-row">
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{container.name}</span>
                    {container.compose_service ? (
                      <Badge variant="secondary" className="text-[10px]">
                        {container.compose_service}
                      </Badge>
                    ) : null}
                  </div>
                  {container.compose_project ? (
                    <p className="text-[11px] text-muted-foreground">
                      {container.compose_project}
                    </p>
                  ) : null}
                </TableCell>
                <TableCell className="max-w-[220px] truncate font-mono text-xs">
                  {container.image}
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={cn("gap-1.5", status.className)}
                    data-testid="container-status"
                  >
                    <span className="size-1.5 rounded-full bg-current" />
                    {status.label}
                  </Badge>
                </TableCell>
                <TableCell data-testid="container-health">
                  {health ? (
                    <Badge variant="outline" className={cn("gap-1.5", health.className)}>
                      <span className="size-1.5 rounded-full bg-current" />
                      {health.label}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">Tanpa healthcheck</span>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {container.ports.length === 0 ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : (
                      container.ports.map((port) => (
                        <Badge
                          key={`${port.container_port}/${port.protocol}/${port.host_port ?? "exposed"}`}
                          variant="outline"
                          className={cn(
                            "font-mono text-[10px]",
                            port.host_port === null
                              ? "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300"
                              : "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
                          )}
                          title={
                            port.host_port === null
                              ? `Port ${port.container_port}/${port.protocol} (exposed, tidak dipublish)`
                              : `Host ${port.host_port} → container ${port.container_port}/${port.protocol}`
                          }
                        >
                          {port.host_port === null
                            ? `${port.container_port}/${port.protocol}`
                            : `${port.host_port}→${port.container_port}/${port.protocol}`}
                        </Badge>
                      ))
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums">
                  {container.restart_count}
                </TableCell>
                <TableCell>
                  <UsageBar
                    label="CPU"
                    value={container.cpu_percent === null ? "—" : `${container.cpu_percent.toFixed(1)}%`}
                    percent={(cpuPercent / maxCpu) * 100}
                    color="var(--chart-1)"
                    testId="container-cpu"
                  />
                </TableCell>
                <TableCell>
                  <UsageBar
                    label="RAM"
                    value={
                      container.memory_usage_bytes === null
                        ? "—"
                        : formatBytes(container.memory_usage_bytes)
                    }
                    percent={memoryPercent}
                    color="var(--chart-2)"
                    testId="container-memory"
                  />
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {busy ? (
                      <Loader2Icon className="size-4 animate-spin text-muted-foreground" />
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Start container"
                      aria-label={`Start ${container.name}`}
                      disabled={busy || isRunning}
                      onClick={() => onStart(container)}
                    >
                      <Play />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Stop container"
                      aria-label={`Stop ${container.name}`}
                      disabled={busy || !isRunning}
                      onClick={() => onStop(container)}
                    >
                      <Square />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Restart container"
                      aria-label={`Restart ${container.name}`}
                      disabled={busy || !isRunning}
                      onClick={() => onRestart(container)}
                    >
                      <RotateCw />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Inspect container"
                      aria-label={`Inspect ${container.name}`}
                      onClick={() => onInspect(container)}
                    >
                      <ScanSearch />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  )
}
