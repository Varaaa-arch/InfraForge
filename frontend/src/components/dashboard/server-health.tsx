import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowRight, ServerOff } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchServers } from "@/api/servers";
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
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Server, ServerStatus } from "@/types/server";

const statusStyles: Record<ServerStatus, { label: string; className: string }> = {
  active: {
    label: "Active",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  inactive: {
    label: "Inactive",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  error: {
    label: "Error",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

function ServerRow({ server }: { server: Server }) {
  const status = statusStyles[server.status];

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border bg-muted/20 px-3 py-2.5"
      data-testid="server-health-row"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{server.name}</p>
        <p className="truncate font-mono text-xs text-muted-foreground">
          {server.host}:{server.port}
        </p>
      </div>

      <Badge variant="outline" className={cn("gap-1.5", status.className)}>
        <span className="size-1.5 rounded-full bg-current" />
        {status.label}
      </Badge>

      {server.exporter_instance ? (
        <Badge
          variant="outline"
          className="hidden border-indigo-500/30 bg-indigo-500/10 text-indigo-600 sm:inline-flex dark:text-indigo-400"
          title={`Exporter: ${server.exporter_instance}`}
        >
          Metrik aktif
        </Badge>
      ) : (
        <span className="hidden text-xs text-muted-foreground sm:inline">Tanpa exporter</span>
      )}

      {server.exporter_instance ? (
        <Button asChild variant="outline" size="sm">
          <Link to={`/monitoring?server=${server.id}`}>
            Grafik
            <ArrowRight className="size-3.5" />
          </Link>
        </Button>
      ) : (
        <Button variant="outline" size="sm" disabled title="Isi exporter_instance untuk mengaktifkan metrik">
          Grafik
        </Button>
      )}
    </div>
  );
}

export function ServerHealth() {
  const query = useQuery({
    queryKey: ["servers"],
    queryFn: fetchServers,
    refetchInterval: 30_000,
    retry: 1,
  });

  const errorMessage = query.error
    ? query.error instanceof ApiError
      ? query.error.message
      : "Tidak dapat memuat daftar server."
    : null;
  const servers = query.data ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle className="text-base">Status kesehatan server</CardTitle>
          <CardDescription>
            Pantau status SSH dan ketersediaan metrik Prometheus setiap server.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {query.isPending ? (
          [0, 1].map((index) => <Skeleton key={index} className="h-[62px] w-full rounded-lg" />)
        ) : errorMessage ? (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <p className="text-sm text-destructive">{errorMessage}</p>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              Coba lagi
            </Button>
          </div>
        ) : servers.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <ServerOff className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada server</p>
            <p className="text-xs text-muted-foreground">
              Tambahkan server terlebih dahulu untuk mulai memantau metrik.
            </p>
          </div>
        ) : (
          servers.map((server) => <ServerRow key={server.id} server={server} />)
        )}
      </CardContent>
    </Card>
  );
}

export function MonitoringShortcutCard() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm font-medium">Monitoring</CardTitle>
        <Activity className="size-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm">Grafik CPU, RAM, disk, dan jaringan dari Prometheus.</p>
        <Button asChild variant="outline" size="sm" className="w-full justify-between">
          <Link to="/monitoring">
            Buka monitoring
            <ArrowRight className="size-3.5" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
