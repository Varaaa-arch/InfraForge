import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { BellOff, CheckCircle2, RefreshCw } from "lucide-react";
import { useState } from "react";

import { fetchAlerts } from "@/api/alerts";
import { ApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { AlertEvent, AlertStatus } from "@/types/alert";

const dateFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
});

const severityStyles: Record<string, string> = {
  critical: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  unknown: "border-border text-muted-foreground",
};

function formatDate(iso: string): string {
  return dateFormatter.format(new Date(iso));
}

function formatRelative(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) {
    return "baru saja";
  }
  if (minutes < 60) {
    return `${minutes} menit lalu`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} jam lalu`;
  }
  return `${Math.round(hours / 24)} hari lalu`;
}

function formatDuration(start: string, end: string | null): string {
  const startMs = new Date(start).getTime();
  const endMs = end ? new Date(end).getTime() : Date.now();
  const minutes = Math.max(0, Math.round((endMs - startMs) / 60_000));

  if (minutes < 1) {
    return "< 1 menit";
  }
  if (minutes < 60) {
    return `${minutes} menit`;
  }

  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) {
    return restMinutes ? `${hours} jam ${restMinutes} menit` : `${hours} jam`;
  }

  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} hari ${restHours} jam` : `${days} hari`;
}

function getService(labels: Record<string, string>): string {
  return (
    labels.service ??
    labels.job ??
    labels.instance ??
    labels.component ??
    labels.container ??
    "—"
  );
}

function StatusBadge({ status }: { status: AlertStatus }) {
  if (status === "firing") {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
      >
        <span className="relative flex size-1.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500 opacity-70" />
          <span className="relative inline-flex size-1.5 rounded-full bg-red-500" />
        </span>
        Firing
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
    >
      <CheckCircle2 className="size-3" />
      Resolved
    </Badge>
  );
}

function LabelChips({ labels }: { labels: Record<string, string> }) {
  const entries = Object.entries(labels)
    .filter(([key]) => key !== "alertname" && key !== "severity")
    .slice(0, 3);

  if (entries.length === 0) {
    return null;
  }

  return (
    <>
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[0.65rem] text-muted-foreground"
          title={`${key}=${value}`}
        >
          {key}={value}
        </span>
      ))}
    </>
  );
}

function AlertRow({ alert }: { alert: AlertEvent }) {
  return (
    <TableRow data-testid="alert-row">
      <TableCell className="px-3">
        <StatusBadge status={alert.status} />
      </TableCell>
      <TableCell className="px-3">
        <Badge
          variant="outline"
          className={severityStyles[alert.severity] ?? severityStyles.unknown}
        >
          {alert.severity}
        </Badge>
      </TableCell>
      <TableCell className="max-w-[360px] px-3 whitespace-normal">
        <p className="text-sm font-medium">{alert.alert_name}</p>
        {alert.summary ? (
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{alert.summary}</p>
        ) : null}
        <div className="mt-1 flex flex-wrap gap-1">
          <LabelChips labels={alert.labels} />
        </div>
      </TableCell>
      <TableCell className="hidden px-3 md:table-cell">
        <span className="font-mono text-xs text-muted-foreground" title={getService(alert.labels)}>
          {getService(alert.labels)}
        </span>
      </TableCell>
      <TableCell className="px-3 text-xs text-muted-foreground" title={formatDate(alert.starts_at)}>
        {formatRelative(alert.starts_at)}
      </TableCell>
      <TableCell className="hidden px-3 text-xs text-muted-foreground lg:table-cell">
        {formatDuration(alert.starts_at, alert.ends_at)}
        {alert.status === "firing" ? " · berlangsung" : ""}
      </TableCell>
    </TableRow>
  );
}

export function AlertHistory() {
  const [status, setStatus] = useState<AlertStatus | "all">("all");
  const [severity, setSeverity] = useState("all");

  const query = useQuery({
    queryKey: ["alerts", "list", status, severity],
    queryFn: () =>
      fetchAlerts({
        status: status === "all" ? undefined : status,
        severity: severity === "all" ? undefined : severity,
        limit: 100,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  });

  const errorMessage = query.error
    ? query.error instanceof ApiError
      ? query.error.message
      : "Tidak dapat memuat riwayat alert."
    : null;
  const alerts = query.data ?? [];

  return (
    <div className="space-y-3">
      <Card size="sm">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <Select
            value={status}
            onValueChange={(value) => setStatus(value as AlertStatus | "all")}
          >
            <SelectTrigger className="w-[144px]" aria-label="Filter status alert">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua status</SelectItem>
              <SelectItem value="firing">Firing</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
            </SelectContent>
          </Select>

          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className="w-[144px]" aria-label="Filter severity alert">
              <SelectValue placeholder="Severity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua severity</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="info">Info</SelectItem>
            </SelectContent>
          </Select>

          <Button
            variant="outline"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <RefreshCw className={cn("size-3.5", query.isFetching && "animate-spin")} />
            Muat ulang
          </Button>

          <span className="ml-auto text-xs text-muted-foreground">
            {query.data?.length ?? 0} alert
          </span>
        </CardContent>
      </Card>

      {query.isPending ? (
        <div className="overflow-hidden rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          <div className="space-y-3">
            {[0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-10 w-full rounded-md" />
            ))}
          </div>
        </div>
      ) : errorMessage ? (
        <Card size="sm">
          <CardContent className="flex flex-col items-center gap-2 p-6 text-center">
            <p className="text-sm text-destructive">{errorMessage}</p>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : alerts.length === 0 ? (
        <Card size="sm">
          <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
            <BellOff className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada alert</p>
            <p className="text-xs text-muted-foreground">
              Alert akan muncul di sini setelah Prometheus mengevaluasi rules dan mengirimnya ke
              Alertmanager.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-hidden rounded-xl bg-card text-sm ring-1 ring-foreground/10">
          <Table data-testid="alert-table">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="px-3">Status</TableHead>
                <TableHead className="px-3">Severity</TableHead>
                <TableHead className="px-3">Alert</TableHead>
                <TableHead className="hidden px-3 md:table-cell">Service</TableHead>
                <TableHead className="px-3">Waktu</TableHead>
                <TableHead className="hidden px-3 lg:table-cell">Durasi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {alerts.map((alert) => (
                <AlertRow key={alert.id} alert={alert} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
