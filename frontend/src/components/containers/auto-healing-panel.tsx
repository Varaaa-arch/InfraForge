import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CircleCheck,
  HeartPulse,
  Loader2Icon,
  RefreshCw,
  Settings2,
  TriangleAlert,
  Wrench,
} from "lucide-react";

import { fetchContainerIncidents, fetchContainerPolicies } from "@/api/container-policies";
import { ApiError } from "@/api/client";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePermissions } from "@/hooks/use-permissions";
import { cn } from "@/lib/utils";
import type { ContainerIncident } from "@/types/container";

interface PolicyTarget {
  id: string;
  name: string;
}

interface AutoHealingPanelProps {
  onConfigure: (container: PolicyTarget) => void;
}

const incidentStyles: Record<
  string,
  { label: string; className: string; icon: typeof HeartPulse }
> = {
  CONTAINER_UNHEALTHY: {
    label: "Unhealthy",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
    icon: TriangleAlert,
  },
  CONTAINER_AUTO_RESTART: {
    label: "Auto-restart",
    className: "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
    icon: Wrench,
  },
  CONTAINER_RECOVERED: {
    label: "Recovered",
    className:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    icon: CircleCheck,
  },
};

function formatDateTime(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function incidentSummary(incident: ContainerIncident): string {
  const details = incident.details ?? {};
  if (incident.action === "CONTAINER_UNHEALTHY") {
    return `Streak ${String(details.streak ?? "?")}/${String(details.threshold ?? "?")}`;
  }
  if (incident.action === "CONTAINER_AUTO_RESTART") {
    const result = details.result === "failed" ? "gagal" : "berhasil";
    return `Restart ${result} (${String(details.restart_count_window ?? "?")}/${String(details.max_restarts ?? "?")})`;
  }
  if (incident.action === "CONTAINER_RECOVERED") {
    return `Health ${String(details.previous_health ?? "?")} → ${String(details.health ?? "?")}`;
  }
  return "—";
}

export function AutoHealingPanel({ onConfigure }: AutoHealingPanelProps) {
  const { canDeploy } = usePermissions();
  const policiesQuery = useQuery({
    queryKey: ["container-policies"],
    queryFn: fetchContainerPolicies,
    refetchInterval: 30_000,
    retry: 1,
  });
  const incidentsQuery = useQuery({
    queryKey: ["container-incidents"],
    queryFn: () => fetchContainerIncidents(undefined, 25),
    refetchInterval: 30_000,
    retry: 1,
  });

  const worker = policiesQuery.data?.worker;
  const policies = policiesQuery.data?.items ?? [];
  const incidents = incidentsQuery.data ?? [];
  const error = policiesQuery.error
    ? policiesQuery.error instanceof ApiError
      ? policiesQuery.error.message
      : "Gagal memuat status auto-healing."
    : null;

  return (
    <div className="space-y-4" data-testid="auto-heal-panel">
      <Card size="sm">
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="size-4" />
              Worker auto-healing
            </CardTitle>
            <CardDescription>
              Health polling backend dan ringkasan insiden terbaru.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void policiesQuery.refetch();
              void incidentsQuery.refetch();
            }}
            disabled={policiesQuery.isFetching || incidentsQuery.isFetching}
          >
            <RefreshCw
              className={cn(
                "size-3.5",
                (policiesQuery.isFetching || incidentsQuery.isFetching) && "animate-spin",
              )}
            />
            Muat ulang
          </Button>
        </CardHeader>
        <CardContent>
          {policiesQuery.isPending ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Memuat status worker...
            </div>
          ) : error ? (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <p>{error}</p>
            </div>
          ) : worker ? (
            <div
              className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
              data-testid="auto-heal-worker"
            >
              <div className="rounded-lg border px-3 py-2">
                <p className="text-xs text-muted-foreground">Status worker</p>
                <Badge
                  variant="outline"
                  className={cn(
                    "mt-1",
                    worker.enabled && worker.running
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
                  )}
                >
                  {worker.enabled
                    ? worker.running
                      ? "Aktif"
                      : "Nonaktif sementara"
                    : "Dimatikan"}
                </Badge>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-xs text-muted-foreground">Interval polling</p>
                <p className="mt-1 text-sm font-medium tabular-nums">
                  {worker.interval_seconds} detik
                </p>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-xs text-muted-foreground">Poll terakhir</p>
                <p className="mt-1 text-sm font-medium">
                  {formatDateTime(worker.last_poll_at)}
                </p>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-xs text-muted-foreground">Siklus terakhir</p>
                <p className="mt-1 text-xs font-medium">
                  {worker.last_stats
                    ? `${worker.last_stats.checked ?? 0} dicek · ${
                        worker.last_stats.restarted ?? 0
                      } restart`
                    : worker.last_error ?? "Belum ada siklus"}
                </p>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Policy auto-healing</CardTitle>
            <CardDescription>
              Aktifkan auto-healing lewat tombol atur pada container di tab Containers.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {policiesQuery.isPending ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Memuat policy...
            </div>
          ) : policies.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <HeartPulse className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">Belum ada policy container</p>
              <p className="max-w-md text-xs text-muted-foreground">
                Buka tab Containers, pilih container, lalu atur resource dan
                aktifkan auto-healing.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table data-testid="auto-heal-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Container</TableHead>
                    <TableHead>Auto-healing</TableHead>
                    <TableHead>Health terakhir</TableHead>
                    <TableHead>Streak</TableHead>
                    <TableHead>Restart window</TableHead>
                    <TableHead>Restart terakhir</TableHead>
                    <TableHead className="text-right">Aksi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {policies.map((policy) => (
                    <TableRow key={policy.id} data-testid="auto-heal-row">
                      <TableCell>
                        <p className="font-medium">{policy.container_name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {policy.compose_project ?? "tanpa project"}
                        </p>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn(
                            policy.auto_heal_enabled
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
                          )}
                        >
                          {policy.auto_heal_enabled ? "Aktif" : "Nonaktif"}
                        </Badge>
                        {policy.auto_heal_enabled ? (
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            ambang {policy.unhealthy_threshold} · maks{" "}
                            {policy.max_restarts} restart
                          </p>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        {policy.last_health_status ?? "—"}
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {policy.unhealthy_streak}
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {policy.restart_count_window}/{policy.max_restarts}
                      </TableCell>
                      <TableCell>{formatDateTime(policy.last_restart_at)}</TableCell>
                      <TableCell className="text-right">
                        {canDeploy ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              onConfigure({
                                id: policy.container_id ?? policy.container_name,
                                name: policy.container_name,
                              })
                            }
                            aria-label={`Atur policy ${policy.container_name}`}
                            data-testid="auto-heal-configure"
                          >
                            <Settings2 />
                            Atur
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Insiden terbaru</CardTitle>
            <CardDescription>
              Dicatat sebagai system event di Audit Logs (maksimal 25 terakhir).
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {incidentsQuery.isPending ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Memuat insiden...
            </div>
          ) : incidents.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Belum ada insiden auto-healing.
            </p>
          ) : (
            <ul className="space-y-2" data-testid="auto-heal-incidents">
              {incidents.map((incident) => {
                const style = incidentStyles[incident.action] ?? {
                  label: incident.action,
                  className: "border-slate-500/30 bg-slate-500/10",
                  icon: Activity,
                };
                const Icon = style.icon;
                return (
                  <li
                    key={incident.id}
                    className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm"
                    data-testid="auto-heal-incident"
                  >
                    <Badge variant="outline" className={cn("gap-1.5", style.className)}>
                      <Icon className="size-3" />
                      {style.label}
                    </Badge>
                    <span className="font-medium">
                      {incident.container_name ?? "container"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {incidentSummary(incident)}
                    </span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatDateTime(incident.created_at)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
