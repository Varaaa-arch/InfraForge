import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Boxes,
  CircleCheck,
  Filter,
  Play,
  RefreshCw,
  Search,
  Square,
  TriangleAlert,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import {
  fetchContainers,
  restartContainer,
  startContainer,
  stopContainer,
} from "@/api/containers";
import { ContainerTable } from "@/components/containers/container-table";
import { InspectDialog } from "@/components/containers/inspect-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Container } from "@/types/container";

type StatusFilter = "all" | "running" | "stopped";

type PendingAction = "start" | "stop" | "restart";

interface Notice {
  tone: "success" | "error";
  text: string;
}

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Semua status" },
  { value: "running", label: "Running" },
  { value: "stopped", label: "Berhenti" },
];

export function ContainersPage() {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busyContainerId, setBusyContainerId] = useState<string | null>(null);
  const [pending, setPending] = useState<{
    action: PendingAction;
    container: Container;
  } | null>(null);
  const [inspecting, setInspecting] = useState<Container | null>(null);

  const containersQuery = useQuery({
    queryKey: ["containers"],
    queryFn: () => fetchContainers(true),
    refetchInterval: 20_000,
    retry: 1,
  });

  const lifecycleMutation = useMutation({
    mutationFn: async (input: { action: PendingAction; container: Container }) => {
      const { action, container } = input;
      if (action === "stop") {
        return stopContainer(container.id);
      }
      if (action === "restart") {
        return restartContainer(container.id);
      }
      return startContainer(container.id);
    },
    onSuccess: (_result, input) => {
      setBusyContainerId(null);
      setPending(null);
      const verb =
        input.action === "stop"
          ? "dihentikan"
          : input.action === "restart"
            ? "direstart"
            : "dijalankan";
      setNotice({
        tone: "success",
        text: `Container ${input.container.name} berhasil ${verb}.`,
      });
      void queryClient.invalidateQueries({ queryKey: ["containers"] });
    },
    onError: (error) => {
      setBusyContainerId(null);
      setPending(null);
      setNotice({
        tone: "error",
        text:
          error instanceof ApiError ? error.message : "Gagal menjalankan aksi container.",
      });
    },
  });

  const containers = useMemo(() => containersQuery.data ?? [], [containersQuery.data]);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    return containers.filter((container) => {
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "running"
          ? container.status === "running"
          : container.status !== "running");

      if (!matchesStatus) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      return (
        container.name.toLowerCase().includes(keyword) ||
        container.image.toLowerCase().includes(keyword) ||
        (container.compose_project ?? "").toLowerCase().includes(keyword)
      );
    });
  }, [containers, search, statusFilter]);

  const runningCount = containers.filter((item) => item.status === "running").length;
  const stoppedCount = containers.length - runningCount;

  const listError = containersQuery.error
    ? containersQuery.error instanceof ApiError
      ? containersQuery.error.message
      : "Tidak dapat memuat daftar container."
    : null;

  function runAction(action: PendingAction, container: Container) {
    setBusyContainerId(container.id);
    lifecycleMutation.mutate({ action, container });
  }

  return (
    <div className="space-y-6" data-testid="containers-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Containers</h1>
          <p className="text-sm text-muted-foreground">
            Daftar container Docker beserta health, port mapping, dan pemakaian CPU/RAM.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          >
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
              <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500" />
            </span>
            Auto-refresh 20 detik
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void containersQuery.refetch()}
            disabled={containersQuery.isFetching}
          >
            <RefreshCw className={cn("size-3.5", containersQuery.isFetching && "animate-spin")} />
            Muat ulang
          </Button>
        </div>
      </div>

      {notice ? (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
            notice.tone === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
          )}
          data-testid="container-notice"
        >
          {notice.tone === "success" ? (
            <CircleCheck className="mt-0.5 size-4 shrink-0" />
          ) : (
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          )}
          <p className="flex-1">{notice.text}</p>
          <button
            type="button"
            onClick={() => setNotice(null)}
            aria-label="Tutup notifikasi"
            className="shrink-0 opacity-70 transition-opacity hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Total container</CardTitle>
            <Boxes className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums" data-testid="stat-total">
              {containersQuery.isPending ? "—" : containers.length}
            </p>
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Running</CardTitle>
            <Play className="size-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums" data-testid="stat-running">
              {containersQuery.isPending ? "—" : runningCount}
            </p>
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-medium">Berhenti</CardTitle>
            <Square className="size-4 text-slate-500" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums" data-testid="stat-stopped">
              {containersQuery.isPending ? "—" : stoppedCount}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card size="sm">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Cari nama atau image container"
              className="w-[240px] pl-8"
              aria-label="Cari container"
              data-testid="container-search"
            />
          </div>

          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as StatusFilter)}
          >
            <SelectTrigger className="w-[170px]" aria-label="Filter status">
              <Filter className="size-3.5" />
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              {statusFilters.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <span className="ml-auto text-xs text-muted-foreground" data-testid="container-count">
            {filtered.length} dari {containers.length} container
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Daftar container</CardTitle>
            <CardDescription>
              CPU/RAM diambil dari exporter backend via Prometheus (maks. 15 detik).
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {containersQuery.isPending ? (
            <div className="space-y-2">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-14 w-full rounded-lg" />
              ))}
            </div>
          ) : listError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <TriangleAlert className="size-6 text-destructive" />
              <p className="text-sm text-destructive">{listError}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void containersQuery.refetch()}
              >
                Coba lagi
              </Button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Boxes className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">Tidak ada container yang cocok</p>
              <p className="max-w-md text-xs text-muted-foreground">
                Ubah kata kunci pencarian atau filter status untuk melihat container lain.
              </p>
            </div>
          ) : (
            <ContainerTable
              containers={filtered}
              busyContainerId={busyContainerId}
              onStart={(container) => runAction("start", container)}
              onStop={(container) => setPending({ action: "stop", container })}
              onRestart={(container) => setPending({ action: "restart", container })}
              onInspect={(container) => setInspecting(container)}
            />
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPending(null);
          }
        }}
        title={pending?.action === "restart" ? "Restart container?" : "Stop container?"}
        description={
          pending
            ? `Container "${pending.container.name}" akan ${
                pending.action === "restart" ? "direstart" : "dihentikan"
              }. Service yang bergantung padanya dapat terganggu sebentar.`
            : undefined
        }
        confirmLabel={pending?.action === "restart" ? "Restart" : "Stop"}
        variant={pending?.action === "stop" ? "destructive" : "default"}
        isPending={lifecycleMutation.isPending}
        onConfirm={() => {
          if (pending) {
            runAction(pending.action, pending.container);
          }
        }}
      />

      <InspectDialog
        containerId={inspecting?.id ?? null}
        containerName={inspecting?.name ?? null}
        open={inspecting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setInspecting(null);
          }
        }}
      />
    </div>
  )
}
