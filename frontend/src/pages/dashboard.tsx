import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CircleAlert,
  CircleDashed,
  HeartPulse,
  ScrollText,
  ServerCog,
  UserRound,
} from "lucide-react";
import { Link } from "react-router-dom";

import { apiFetch, API_BASE_URL } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/use-auth";

interface HealthResponse {
  status: string;
}

const roadmap = [
  { label: "REST API logs (Loki)", done: true },
  { label: "WebSocket real-time tail", done: true },
  { label: "Halaman logs interaktif", done: true },
];

export function DashboardPage() {
  const { user } = useAuth();

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
    refetchInterval: 30_000,
    retry: 1,
  });

  const joinedAt = user
    ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium" }).format(new Date(user.created_at))
    : "-";

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Selamat datang{user?.full_name ? `, ${user.full_name}` : user ? `, ${user.username}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">
          Ringkasan platform InfraForge dan akses cepat ke fitur observability.
        </p>
      </div>

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

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Roadmap Logging</CardTitle>
            <ServerCog className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-1.5">
            {roadmap.map((item) => (
              <div key={item.label} className="flex items-center gap-2 text-xs">
                {item.done ? (
                  <Check className="size-3.5 text-emerald-500" />
                ) : (
                  <CircleDashed className="size-3.5 text-muted-foreground" />
                )}
                <span className={item.done ? "text-muted-foreground line-through" : ""}>
                  {item.label}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mulai dari sini</CardTitle>
          <CardDescription>
            Backend, Loki, WebSocket, dan halaman logs interaktif sudah aktif. Gunakan filter
            container, level, keyword, atau live tail untuk menelusuri log.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link to="/logs">
              Lihat halaman Logs
              <ArrowRight className="size-3.5" />
            </Link>
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
