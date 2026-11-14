import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Pencil,
  Plus,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import {
  bulkUpsertEnvVars,
  deleteEnvVar,
  fetchEnvVars,
  revealEnvVar,
  updateEnvVar,
} from "@/api/projects";
import { EnvVarFormDialog, type EnvVarFormValues } from "@/components/projects/env-var-form-dialog";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { EnvVarMasked } from "@/types/project";

const timeFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
});

interface Notice {
  tone: "success" | "error";
  text: string;
}

interface EnvVarsPanelProps {
  projectId: number;
  onOpenBulkImport: () => void;
}

export function EnvVarsPanel({ projectId, onOpenBulkImport }: EnvVarsPanelProps) {
  const queryClient = useQueryClient();

  const envQuery = useQuery({
    queryKey: ["env-vars", projectId],
    queryFn: () => fetchEnvVars(projectId),
    refetchInterval: 20_000,
    retry: 1,
  });

  const [revealed, setRevealed] = useState<Record<number, string>>({});
  const [revealTarget, setRevealTarget] = useState<EnvVarMasked | null>(null);
  const [editing, setEditing] = useState<EnvVarMasked | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<EnvVarMasked | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const revealMutation = useMutation({
    mutationFn: (envVar: EnvVarMasked) => revealEnvVar(projectId, envVar.id),
    onSuccess: (result) => {
      setRevealed((previous) => ({ ...previous, [result.id]: result.value }));
      setRevealTarget(null);
    },
    onError: (error) => {
      setRevealTarget(null);
      setNotice({
        tone: "error",
        text:
          error instanceof ApiError ? error.message : "Gagal membuka nilai environment variable.",
      });
    },
  });

  const saveMutation = useMutation({
    mutationFn: async (payload: EnvVarFormValues) => {
      if (editing) {
        await updateEnvVar(projectId, editing.id, payload.value);
        return;
      }
      await bulkUpsertEnvVars(projectId, [
        { key: payload.key as string, value: payload.value },
      ]);
    },
    onSuccess: () => {
      setEditing(null);
      setCreating(false);
      setFormError(null);
      setNotice({ tone: "success", text: "Environment variable berhasil disimpan." });
      void queryClient.invalidateQueries({ queryKey: ["env-vars", projectId] });
    },
    onError: (error) => {
      setFormError(
        error instanceof ApiError ? error.message : "Gagal menyimpan environment variable.",
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (envId: number) => deleteEnvVar(projectId, envId),
    onSuccess: () => {
      setDeleting(null);
      setNotice({ tone: "success", text: "Environment variable berhasil dihapus." });
      void queryClient.invalidateQueries({ queryKey: ["env-vars", projectId] });
    },
    onError: (error) => {
      setDeleting(null);
      setNotice({
        tone: "error",
        text:
          error instanceof ApiError ? error.message : "Gagal menghapus environment variable.",
      });
    },
  });

  const envVars = envQuery.data?.env_vars ?? [];
  const lastDeploymentAt = envQuery.data?.last_deployment_at ?? null;
  const pendingCount = envVars.filter((item) => item.pending_redeploy).length;

  const listError = envQuery.error
    ? envQuery.error instanceof ApiError
      ? envQuery.error.message
      : "Tidak dapat memuat environment variable."
    : null;

  return (
    <div className="space-y-4">
      {notice ? (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
            notice.tone === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
          )}
          data-testid="env-var-notice"
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

      {pendingCount > 0 ? (
        <div
          className="flex flex-col gap-1 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
          data-testid="redeploy-banner"
        >
          <p className="font-medium">
            {pendingCount} variabel diubah setelah deployment terakhir
            {lastDeploymentAt
              ? ` (${timeFormatter.format(new Date(lastDeploymentAt))})`
              : ""}
            — perlu re-deploy agar nilai baru terpasang.
          </p>
          <p className="text-xs opacity-80">
            Environment variable berlaku untuk semua aplikasi di project ini.
          </p>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="space-y-1">
              <CardTitle className="text-base">Environment variables</CardTitle>
              <CardDescription>
                Nilai tersimpan terenkripsi dan ditampilkan dalam bentuk tersamar. Ubah nilai
                bila perlu, lalu deploy ulang aplikasi agar nilai baru dipakai.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenBulkImport}
                data-testid="env-bulk-import-button"
              >
                <Upload />
                Bulk import .env
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  setEditing(null);
                  setFormError(null);
                  setCreating(true);
                }}
                data-testid="env-var-add-button"
              >
                <Plus />
                Tambah variabel
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {envQuery.isPending ? (
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
                onClick={() => void envQuery.refetch()}
              >
                Coba lagi
              </Button>
            </div>
          ) : envVars.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <KeyRound className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">Belum ada environment variable</p>
              <p className="max-w-md text-xs text-muted-foreground">
                Tambahkan satu per satu atau bulk import dari file .env.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table data-testid="env-var-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Key</TableHead>
                    <TableHead>Nilai</TableHead>
                    <TableHead>Diperbarui</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Aksi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {envVars.map((envVar) => {
                    const plain = revealed[envVar.id];

                    return (
                      <TableRow key={envVar.id} data-testid="env-var-row">
                        <TableCell className="font-mono text-xs whitespace-nowrap">
                          {envVar.key}
                        </TableCell>
                        <TableCell
                          className="max-w-[280px] truncate font-mono text-xs"
                          data-testid="env-var-value"
                        >
                          {plain ?? envVar.masked_value}
                        </TableCell>
                        <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                          {timeFormatter.format(new Date(envVar.updated_at))}
                        </TableCell>
                        <TableCell>
                          {envVar.pending_redeploy ? (
                            <Badge
                              variant="outline"
                              className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                              data-testid="env-var-pending"
                            >
                              Perlu re-deploy
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            >
                              Terpasang
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            {plain ? (
                              <>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  title="Salin nilai"
                                  aria-label={`Salin ${envVar.key}`}
                                  onClick={() => {
                                    void navigator.clipboard?.writeText(plain);
                                    setNotice({ tone: "success", text: `${envVar.key} disalin.` });
                                  }}
                                >
                                  <Copy />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  title="Sembunyikan nilai"
                                  aria-label={`Sembunyikan ${envVar.key}`}
                                  onClick={() => {
                                    setRevealed((previous) => {
                                      const next = { ...previous };
                                      delete next[envVar.id];
                                      return next;
                                    });
                                  }}
                                >
                                  <EyeOff />
                                </Button>
                              </>
                            ) : (
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                title="Tampilkan nilai"
                                aria-label={`Tampilkan ${envVar.key}`}
                                disabled={revealMutation.isPending}
                                onClick={() => setRevealTarget(envVar)}
                              >
                                <Eye />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              title="Ubah nilai"
                              aria-label={`Ubah ${envVar.key}`}
                              onClick={() => {
                                setFormError(null);
                                setEditing(envVar);
                              }}
                            >
                              <Pencil />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="text-destructive"
                              title="Hapus variabel"
                              aria-label={`Hapus ${envVar.key}`}
                              onClick={() => setDeleting(envVar)}
                            >
                              <X />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={revealTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRevealTarget(null);
          }
        }}
        title="Tampilkan nilai rahasia?"
        description={
          revealTarget
            ? `Nilai ${revealTarget.key} akan ditampilkan sementara di layar dan penampilannya tercatat di audit log.`
            : undefined
        }
        confirmLabel="Tampilkan"
        isPending={revealMutation.isPending}
        onConfirm={() => {
          if (revealTarget) {
            revealMutation.mutate(revealTarget);
          }
        }}
      />

      <EnvVarFormDialog
        key={editing?.id ?? (creating ? "new" : "closed")}
        open={creating || editing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setCreating(false);
            setEditing(null);
            setFormError(null);
          }
        }}
        envVar={editing}
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
        title="Hapus environment variable?"
        description={
          deleting
            ? `${deleting.key} akan dihapus permanen dari project ini. Aplikasi yang memakai nilainya perlu di-deploy ulang.`
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
  )
}
