import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  History,
  RotateCcw,
  ScrollText,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { fetchDeployments, rollbackDeployment } from "@/api/deployments";
import { fetchProjectApplications } from "@/api/projects";
import { DeploymentLogDialog } from "@/components/projects/deployment-log-dialog";
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
import { usePermissions } from "@/hooks/use-permissions";
import { cn } from "@/lib/utils";
import type { Deployment } from "@/types/deployment";

const timeFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "medium",
});

const statusStyles: Record<string, { label: string; className: string }> = {
  pending: {
    label: "Pending",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
  deploying: {
    label: "Deploying",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  success: {
    label: "Success",
    className:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  failed: {
    label: "Failed",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

const triggerLabels: Record<string, string> = {
  manual: "Manual",
  github_webhook: "Webhook",
  ci_token: "CI Token",
};

const ACTIVE_STATUSES = new Set(["pending", "deploying"]);

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)} dtk`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

function versionLabel(deployment: Deployment): string {
  if (deployment.tag) {
    return deployment.tag;
  }
  if (deployment.commit_sha) {
    return deployment.commit_sha.slice(0, 8);
  }
  return `deployment #${deployment.id}`;
}

function hasActiveDeployment(deployments: Deployment[] | undefined): boolean {
  return deployments?.some((item) => ACTIVE_STATUSES.has(item.status)) ?? false;
}

function Feedback({ type, message }: { type: "success" | "error"; message: string }) {
  return (
    <div
      className={cn(
        "mb-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
        type === "success"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border-destructive/30 bg-destructive/10 text-destructive",
      )}
      data-testid="deployment-feedback"
    >
      {type === "success" ? (
        <CheckCircle2 className="size-4 shrink-0" />
      ) : (
        <XCircle className="size-4 shrink-0" />
      )}
      {message}
    </div>
  );
}

interface DeploymentHistoryProps {
  projectId: number;
  canViewLogs: boolean;
}

export function DeploymentHistory({
  projectId,
  canViewLogs,
}: DeploymentHistoryProps) {
  const queryClient = useQueryClient();
  const { canDeploy } = usePermissions();
  const [rollbackTarget, setRollbackTarget] = useState<Deployment | null>(null);
  const [logTarget, setLogTarget] = useState<Deployment | null>(null);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const deploymentsQuery = useQuery({
    queryKey: ["deployments", "project", projectId],
    queryFn: () => fetchDeployments({ projectId, limit: 50 }),
    refetchInterval: (query) =>
      hasActiveDeployment(query.state.data) ? 5_000 : 30_000,
    retry: 1,
  });

  const applicationsQuery = useQuery({
    queryKey: ["project-applications", projectId],
    queryFn: () => fetchProjectApplications(projectId),
    refetchInterval: 30_000,
    retry: 1,
  });

  const rollbackMutation = useMutation({
    mutationFn: (target: Deployment) => rollbackDeployment(target.id),
    onSuccess: (rollback, target) => {
      setRollbackTarget(null);
      setFeedback({
        type: "success",
        message: `Rollback #${rollback.id} ke ${versionLabel(target)} dijadwalkan.`,
      });
      void queryClient.invalidateQueries({
        queryKey: ["deployments", "project", projectId],
      });
    },
    onError: (error) => {
      setRollbackTarget(null);
      setFeedback({
        type: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "Gagal menjadwalkan rollback deployment.",
      });
    },
  });

  const deployments = deploymentsQuery.data ?? [];
  const applicationNames = new Map(
    (applicationsQuery.data ?? []).map((app) => [app.id, app.name]),
  );
  const logDeployment =
    logTarget === null
      ? null
      : (deployments.find((deployment) => deployment.id === logTarget.id) ??
        logTarget);
  const latestSuccessByApplication = new Map<number, number>();
  const activeApplicationIds = new Set(
    deployments
      .filter((deployment) => ACTIVE_STATUSES.has(deployment.status))
      .map((deployment) => deployment.application_id),
  );

  for (const deployment of deployments) {
    if (
      deployment.status === "success" &&
      !latestSuccessByApplication.has(deployment.application_id)
    ) {
      latestSuccessByApplication.set(deployment.application_id, deployment.id);
    }
  }

  const listError = deploymentsQuery.error
    ? deploymentsQuery.error instanceof ApiError
      ? deploymentsQuery.error.message
      : "Tidak dapat memuat riwayat deployment."
    : null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4" />
            Riwayat deployment
          </CardTitle>
          <CardDescription>
            Versi rilis lengkap dengan tag, commit, pemicu, dan rollback instan ke
            versi stabil sebelumnya. Status diperbarui otomatis setiap 5 detik selama
            masih ada proses berjalan.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {feedback ? (
            <Feedback type={feedback.type} message={feedback.message} />
          ) : null}
          {deploymentsQuery.isPending ? (
            <div className="space-y-2">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-11 w-full rounded-lg" />
              ))}
            </div>
          ) : listError ? (
            <div
              className="flex flex-col items-center gap-2 py-8 text-center"
              data-testid="deployment-error"
            >
              <TriangleAlert className="size-6 text-destructive" />
              <p className="text-sm text-destructive">{listError}</p>
            </div>
          ) : deployments.length === 0 ? (
            <p
              className="py-6 text-center text-sm text-muted-foreground"
              data-testid="deployment-empty"
            >
              Belum ada deployment. Picu deployment manual atau lewat deployment token
              CI/CD.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table data-testid="deployment-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>Aplikasi</TableHead>
                    <TableHead>Branch</TableHead>
                    <TableHead>Tag</TableHead>
                    <TableHead>Commit</TableHead>
                    <TableHead>Pemicu</TableHead>
                    <TableHead>Waktu rilis</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Durasi</TableHead>
                    <TableHead>Aksi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deployments.map((deployment) => {
                    const status = statusStyles[deployment.status] ?? {
                      label: deployment.status,
                      className:
                        "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
                    };
                    const applicationName =
                      applicationNames.get(deployment.application_id) ??
                      `App #${deployment.application_id}`;
                    const isLatestSuccess =
                      latestSuccessByApplication.get(deployment.application_id) ===
                      deployment.id;
                    const applicationIsActive = activeApplicationIds.has(
                      deployment.application_id,
                    );
                    const canRollback =
                      canDeploy &&
                      deployment.status === "success" &&
                      !isLatestSuccess;
                    const releaseAt =
                      deployment.finished_at ?? deployment.started_at;

                    return (
                      <TableRow key={deployment.id} data-testid="deployment-row">
                        <TableCell className="font-mono text-xs">
                          #{deployment.id}
                        </TableCell>
                        <TableCell className="font-medium">{applicationName}</TableCell>
                        <TableCell className="font-mono text-xs">
                          {deployment.branch}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          <span data-testid="deployment-tag">
                            {deployment.tag ?? "—"}
                          </span>
                        </TableCell>
                        <TableCell
                          className="font-mono text-xs text-muted-foreground"
                          title={deployment.commit_sha ?? undefined}
                        >
                          <span data-testid="deployment-commit">
                            {deployment.commit_sha
                              ? deployment.commit_sha.slice(0, 8)
                              : "—"}
                          </span>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-1">
                            <div className="flex flex-wrap items-center gap-1">
                              <Badge
                                variant="outline"
                                data-testid="deployment-trigger-source"
                              >
                                {triggerLabels[deployment.trigger_source] ??
                                  deployment.trigger_source}
                              </Badge>
                              {deployment.is_rollback ? (
                                <Badge
                                  variant="secondary"
                                  data-testid="deployment-rollback-badge"
                                >
                                  Rollback
                                </Badge>
                              ) : null}
                            </div>
                            <span
                              className="block max-w-44 truncate text-[11px] text-muted-foreground"
                              title={deployment.triggered_by ?? undefined}
                              data-testid="deployment-triggered-by"
                            >
                              {deployment.triggered_by ?? "—"}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell
                          className="text-muted-foreground"
                          title={
                            deployment.finished_at
                              ? `Selesai: ${timeFormatter.format(
                                  new Date(deployment.finished_at),
                                )}`
                              : `Mulai: ${timeFormatter.format(
                                  new Date(deployment.started_at),
                                )}`
                          }
                        >
                          {timeFormatter.format(new Date(releaseAt))}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn("gap-1.5", status.className)}
                            data-testid="deployment-status"
                          >
                            <span className="size-1.5 rounded-full bg-current" />
                            {status.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDuration(deployment.duration)}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1.5">
                            {canViewLogs ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="xs"
                                aria-label={`Lihat log deployment #${deployment.id}`}
                                data-testid="deployment-log-button"
                                onClick={() => setLogTarget(deployment)}
                              >
                                <ScrollText />
                                Log
                              </Button>
                            ) : null}
                            {canRollback ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="xs"
                                disabled={
                                  applicationIsActive || rollbackMutation.isPending
                                }
                                title={
                                  applicationIsActive
                                    ? "Tunggu deployment aplikasi ini selesai"
                                    : `Rollback ke ${versionLabel(deployment)}`
                                }
                                aria-label={`Rollback ${applicationName} ke ${versionLabel(
                                  deployment,
                                )}`}
                                data-testid="deployment-rollback-button"
                                onClick={() => {
                                  setFeedback(null);
                                  setRollbackTarget(deployment);
                                }}
                              >
                                <RotateCcw />
                                Rollback
                              </Button>
                            ) : null}
                            {!canViewLogs && !canRollback ? (
                              <span className="text-xs text-muted-foreground">
                                —
                              </span>
                            ) : null}
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
        open={rollbackTarget !== null}
        onOpenChange={(open) => {
          if (!open && !rollbackMutation.isPending) {
            setRollbackTarget(null);
          }
        }}
        title="Rollback deployment?"
        description={
          rollbackTarget
            ? `${applicationNames.get(rollbackTarget.application_id) ?? `App #${rollbackTarget.application_id}`} akan di-rollback ke ${versionLabel(rollbackTarget)} (commit ${rollbackTarget.commit_sha?.slice(0, 8) ?? "—"}, branch ${rollbackTarget.branch}). Deployment baru dijalankan di background dan versi saat ini tetap aktif sampai health check rollback berhasil.`
            : undefined
        }
        confirmLabel="Rollback"
        isPending={rollbackMutation.isPending}
        onConfirm={() => {
          if (rollbackTarget) {
            rollbackMutation.mutate(rollbackTarget);
          }
        }}
      />

      <DeploymentLogDialog
        key={`deployment-log-${logTarget?.id ?? "none"}-${logTarget ? "open" : "closed"}`}
        deployment={logDeployment}
        applicationName={
          logDeployment
            ? (applicationNames.get(logDeployment.application_id) ??
              `App #${logDeployment.application_id}`)
            : "Aplikasi"
        }
        open={logTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setLogTarget(null);
          }
        }}
      />
    </>
  );
}
