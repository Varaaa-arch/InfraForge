import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AppWindow,
  ArrowRight,
  BellRing,
  Boxes,
  CircleAlert,
  FolderKanban,
  HeartPulse,
  Rocket,
  ScrollText,
  Server,
  UserRound,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { apiFetch, API_BASE_URL } from "@/api/client";
import { MonitoringShortcutCard, ServerHealth } from "@/components/dashboard/server-health";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/use-auth";
import type { DashboardSummary } from "@/types/dashboard";

interface HealthResponse {
  status: string;
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  testId,
  loading,
  error,
}: {
  label: string;
  value?: number;
  hint?: ReactNode;
  icon: typeof Activity;
  testId: string;
  loading: boolean;
  error: boolean;
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className="size-4 text-muted-foreground" />
      </CardHeader>
      <CardContent className="space-y-1">
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <p className="text-2xl font-semibold tabular-nums">
            {error || value === undefined ? "—" : value}
          </p>
        )}
        {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { user } = useAuth();

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
    refetchInterval: 30_000,
    retry: 1,
  });

  const summaryQuery = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => apiFetch<DashboardSummary>("/dashboard"),
    refetchInterval: 30_000,
    retry: 1,
  });

  const summary = summaryQuery.data;
  const statsLoading = summaryQuery.isPending;
  const statsError = summaryQuery.isError;

  const joinedAt = user
    ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium" }).format(new Date(user.created_at))
    : "-";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Selamat datang{user?.full_name ? `, ${user.full_name}` : user ? `, ${user.username}` : ""}
          </h1>
          <p className="text-sm text-muted-foreground">
            Ringkasan platform InfraForge dan akses cepat ke fitur observability.
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

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          label="Applications"
          value={summary?.applications}
          hint={summary ? `${summary.deployments} deployment` : undefined}
          icon={AppWindow}
          testId="stat-application"
          loading={statsLoading}
          error={statsError}
        />
        <StatCard
          label="Server"
          value={summary?.servers}
          hint={
            summary ? (
              <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="inline-flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {summary.servers_active} aktif
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-amber-500" />
                  {summary.servers_inactive} inactive
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-red-500" />
                  {summary.servers_error} error
                </span>
              </span>
            ) : undefined
          }
          icon={Server}
          testId="stat-server"
          loading={statsLoading}
          error={statsError}
        />
        <StatCard
          label="Active alerts"
          value={summary?.alerts_active}
          hint={
            summary ? (
              <span className="flex flex-wrap items-center gap-1.5">
                <Badge
                  variant="outline"
                  className="border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
                >
                  {summary.alerts_critical} critical
                </Badge>
                <Badge
                  variant="outline"
                  className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                >
                  {summary.alerts_warning} warning
                </Badge>
              </span>
            ) : undefined
          }
          icon={BellRing}
          testId="stat-alert-aktif"
          loading={statsLoading}
          error={statsError}
        />
        <StatCard
          label="Project"
          value={summary?.projects}
          hint="Milik akun ini"
          icon={FolderKanban}
          testId="stat-project"
          loading={statsLoading}
          error={statsError}
        />
        <StatCard
          label="Deployment"
          value={summary?.deployments}
          hint="Total riwayat deploy"
          icon={Rocket}
          testId="stat-deployment"
          loading={statsLoading}
          error={statsError}
        />
        <StatCard
          label="Container aktif"
          value={summary?.containers}
          hint={summary ? `Dari ${summary.containers_total} container di host` : undefined}
          icon={Boxes}
          testId="stat-container-aktif"
          loading={statsLoading}
          error={statsError}
        />
      </div>

      <ServerHealth />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Status API</CardTitle>
            <HeartPulse className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-2">
            {healthQuery.isLoading ? (
              <Skeleton className="h-6 w-24" />
            ) : healthQuery.isError ? (
              <Badge variant="destructive" className="gap-1.5">
                <CircleAlert className="size-3" />
                Tidak terhubung
              </Badge>
            ) : (
              <Badge
                variant="outline"
                className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              >
                <span className="size-1.5 rounded-full bg-emerald-500" />
                {healthQuery.data?.status ?? "healthy"}
              </Badge>
            )}
            <p className="text-xs text-muted-foreground">FastAPI · PostgreSQL · Redis</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Centralized Logs</CardTitle>
            <ScrollText className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm">Loki & Promtail siap menerima log container.</p>
            <Button asChild variant="outline" size="sm" className="w-full justify-between">
              <Link to="/logs">
                Buka logs
                <ArrowRight className="size-3.5" />
              </Link>
            </Button>
          </CardContent>
        </Card>

        <MonitoringShortcutCard />

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Sesi Anda</CardTitle>
            <UserRound className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="truncate text-sm font-medium">{user?.username}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
            <p className="text-xs text-muted-foreground">Bergabung {joinedAt}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mulai dari sini</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link to="/monitoring">
              Buka Monitoring
              <ArrowRight className="size-3.5" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to="/logs">Lihat halaman Logs</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to="/alerts">Riwayat alert</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
              Dokumentasi API
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
