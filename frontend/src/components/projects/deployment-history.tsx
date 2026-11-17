import { useQuery } from "@tanstack/react-query";
import { History, TriangleAlert } from "lucide-react";

import { ApiError } from "@/api/client";
import { fetchDeployments } from "@/api/deployments";
import { fetchProjectApplications } from "@/api/projects";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  github_webhook: "GitHub Webhook",
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

function hasActiveDeployment(deployments: Deployment[] | undefined): boolean {
  return deployments?.some((item) => ACTIVE_STATUSES.has(item.status)) ?? false;
}

interface DeploymentHistoryProps {
  projectId: number;
}

export function DeploymentHistory({ projectId }: DeploymentHistoryProps) {
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

  const deployments = deploymentsQuery.data ?? [];
  const applicationNames = new Map(
    (applicationsQuery.data ?? []).map((app) => [app.id, app.name]),
  );

  const listError = deploymentsQuery.error
    ? deploymentsQuery.error instanceof ApiError
      ? deploymentsQuery.error.message
      : "Tidak dapat memuat riwayat deployment."
    : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="size-4" />
          Riwayat deployment
        </CardTitle>
        <CardDescription>
          Status deployment diperbarui otomatis setiap 5 detik selama masih ada proses
          berjalan.
        </CardDescription>
      </CardHeader>
      <CardContent>
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
                  <TableHead>Commit</TableHead>
                  <TableHead>Pemicu</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Durasi</TableHead>
                  <TableHead>Mulai</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deployments.map((deployment) => {
                  const status = statusStyles[deployment.status] ?? {
                    label: deployment.status,
                    className:
                      "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
                  };
                  return (
                    <TableRow key={deployment.id} data-testid="deployment-row">
                      <TableCell className="font-mono text-xs">#{deployment.id}</TableCell>
                      <TableCell className="font-medium">
                        {applicationNames.get(deployment.application_id) ??
                          `App #${deployment.application_id}`}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {deployment.branch}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {deployment.commit_sha
                          ? deployment.commit_sha.slice(0, 8)
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-1">
                          <Badge variant="outline" data-testid="deployment-trigger-source">
                            {triggerLabels[deployment.trigger_source] ??
                              deployment.trigger_source}
                          </Badge>
                          {deployment.is_rollback ? (
                            <Badge variant="secondary">Rollback</Badge>
                          ) : null}
                        </div>
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
                      <TableCell className="text-muted-foreground">
                        {timeFormatter.format(new Date(deployment.started_at))}
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
  );
}
