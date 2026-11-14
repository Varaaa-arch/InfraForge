import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Plus, ServerOff, TriangleAlert, X } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import {
  createServer,
  deleteServer,
  fetchServers,
  testServerConnection,
  updateServer,
} from "@/api/servers";
import { ServerFormDialog } from "@/components/servers/server-form-dialog";
import { ServerTable } from "@/components/servers/server-table";
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
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Server, ServerAuthType } from "@/types/server";

interface ServerFormValues {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: ServerAuthType;
  password?: string;
  private_key?: string;
  exporter_instance?: string;
}

interface Notice {
  tone: "success" | "error";
  text: string;
}

export function ServersPage() {
  const queryClient = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const [editing, setEditing] = useState<Server | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Server | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busyServerId, setBusyServerId] = useState<number | null>(null);

  const serversQuery = useQuery({
    queryKey: ["servers"],
    queryFn: fetchServers,
    refetchInterval: 30_000,
    retry: 1,
  });

  const saveMutation = useMutation({
    mutationFn: (values: ServerFormValues) =>
      editing ? updateServer(editing.id, values) : createServer(values),
    onSuccess: () => {
      setFormOpen(false);
      setEditing(null);
      setNotice({
        tone: "success",
        text: editing ? "Server berhasil diperbarui." : "Server berhasil ditambahkan.",
      });
      void queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
    onError: (error) => {
      setFormError(
        error instanceof ApiError ? error.message : "Gagal menyimpan server.",
      );
    },
  });

  const testMutation = useMutation({
    mutationFn: (serverId: number) => testServerConnection(serverId),
    onSuccess: (result) => {
      setBusyServerId(null);
      setNotice({
        tone: result.success ? "success" : "error",
        text: result.message,
      });
      void queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
    onError: (error) => {
      setBusyServerId(null);
      setNotice({
        tone: "error",
        text:
          error instanceof ApiError ? error.message : "Gagal menguji koneksi server.",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (serverId: number) => deleteServer(serverId),
    onSuccess: () => {
      setNotice({ tone: "success", text: "Server berhasil dihapus." });
      setDeleting(null);
      void queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
    onError: (error) => {
      setNotice({
        tone: "error",
        text: error instanceof ApiError ? error.message : "Gagal menghapus server.",
      });
    },
  });

  const servers = serversQuery.data ?? [];
  const listError = serversQuery.error
    ? serversQuery.error instanceof ApiError
      ? serversQuery.error.message
      : "Tidak dapat memuat daftar server."
    : null;

  function openCreateDialog() {
    setEditing(null);
    setFormError(null);
    setFormKey((key) => key + 1);
    setFormOpen(true);
  }

  function openEditDialog(server: Server) {
    setEditing(server);
    setFormError(null);
    setFormKey((key) => key + 1);
    setFormOpen(true);
  }

  return (
    <div className="space-y-6" data-testid="servers-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Servers</h1>
          <p className="text-sm text-muted-foreground">
            Kelola node/server terdaftar beserta status koneksi Prometheus (exporter).
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
            Auto-refresh 30 detik
          </Badge>
          <Button size="sm" onClick={openCreateDialog} data-testid="add-server-button">
            <Plus />
            Tambah server
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
          data-testid="server-notice"
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

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Daftar server</CardTitle>
            <CardDescription>
              Status Prometheus menunjukkan apakah exporter_instance terdaftar dan hidup di
              Prometheus.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {serversQuery.isPending ? (
            <div className="space-y-2">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-12 w-full rounded-lg" />
              ))}
            </div>
          ) : listError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <TriangleAlert className="size-6 text-destructive" />
              <p className="text-sm text-destructive">{listError}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void serversQuery.refetch()}
              >
                Coba lagi
              </Button>
            </div>
          ) : servers.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <ServerOff className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">Belum ada server</p>
              <p className="max-w-md text-xs text-muted-foreground">
                Tambahkan server agar metrik Prometheus dapat dipantau dan deployment dapat
                diarahkan.
              </p>
              <Button size="sm" onClick={openCreateDialog}>
                <Plus />
                Tambah server
              </Button>
            </div>
          ) : (
            <ServerTable
              servers={servers}
              busyServerId={busyServerId}
              onEdit={openEditDialog}
              onTest={(server) => {
                setBusyServerId(server.id);
                testMutation.mutate(server.id);
              }}
              onDelete={(server) => setDeleting(server)}
            />
          )}
        </CardContent>
      </Card>

      <ServerFormDialog
        key={formKey}
        open={formOpen}
        onOpenChange={setFormOpen}
        server={editing}
        isPending={saveMutation.isPending}
        errorMessage={formError}
        onSubmit={(values) => {
          setFormError(null);
          saveMutation.mutate(values);
        }}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        title="Hapus server?"
        description={
          deleting
            ? `Server "${deleting.name}" akan dihapus permanen dari daftar. Tindakan ini tidak dapat dibatalkan.`
            : undefined
        }
        confirmLabel="Hapus"
        variant="destructive"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deleting) {
            deleteMutation.mutate(deleting.id);
          }
        }}
      />
    </div>
  );
}
