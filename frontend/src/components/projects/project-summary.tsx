import { useQuery } from "@tanstack/react-query";
import { GitBranch, GitFork, Link2, TriangleAlert, Webhook } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { fetchProjectApplications } from "@/api/projects";
import { ApplicationBranchesDialog } from "@/components/projects/application-branches-dialog";
import { RepositoryConnectionDialog } from "@/components/projects/repository-connection-dialog";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { providerLabel } from "@/lib/git-provider";
import { cn } from "@/lib/utils";
import type { Application, Project } from "@/types/project";

const timeFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
});

const appStatusStyles: Record<string, { label: string; className: string }> = {
  running: {
    label: "Running",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  deploying: {
    label: "Deploying",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  failed: {
    label: "Failed",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  idle: {
    label: "Idle",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
};

interface ProjectSummaryProps {
  project: Project;
  canManage: boolean;
}

export function ProjectSummary({ project, canManage }: ProjectSummaryProps) {
  const [repositoryOpen, setRepositoryOpen] = useState(false);
  const [branchesApp, setBranchesApp] = useState<Application | null>(null);
  const appsQuery = useQuery({
    queryKey: ["project-applications", project.id],
    queryFn: () => fetchProjectApplications(project.id),
    refetchInterval: 30_000,
    retry: 1,
  });

  const apps = appsQuery.data ?? [];
  const listError = appsQuery.error
    ? appsQuery.error instanceof ApiError
      ? appsQuery.error.message
      : "Tidak dapat memuat daftar aplikasi."
    : null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="text-base">Informasi project</CardTitle>
              <CardDescription>Repository, branch, dan status environment variable.</CardDescription>
            </div>
            {canManage ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRepositoryOpen(true)}
                data-testid="project-repository-connect"
              >
                <Link2 />
                {project.repository_url ? "Ubah repository" : "Hubungkan repository"}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2">
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Repository</p>
            <p className="flex items-start gap-2">
              <GitFork className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              {project.repository_url ? (
                <a
                  href={project.repository_url}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate font-mono text-xs hover:underline"
                >
                  {project.repository_url}
                </a>
              ) : (
                <span className="truncate text-xs text-muted-foreground">
                  Belum terhubung ke repository
                </span>
              )}
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Branch default</p>
            <p className="flex items-center gap-2">
              <GitBranch className="size-3.5 text-muted-foreground" />
              <span className="font-mono text-xs">{project.default_branch ?? "-"}</span>
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Provider</p>
            <p className="flex items-center gap-2">
              <Link2 className="size-3.5 text-muted-foreground" />
              <span className="text-xs">{providerLabel(project.provider)}</span>
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Terakhir repository terhubung</p>
            <p className="text-xs">
              {project.repository_connected_at
                ? timeFormatter.format(new Date(project.repository_connected_at))
                : "-"}
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Dibuat</p>
            <p className="text-xs">{timeFormatter.format(new Date(project.created_at))}</p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Diperbarui</p>
            <p className="text-xs">{timeFormatter.format(new Date(project.updated_at))}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Aplikasi</CardTitle>
            <CardDescription>
              Aplikasi dalam project ini memakai environment variable yang sama.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {appsQuery.isPending ? (
            <div className="space-y-2">
              {[0, 1].map((index) => (
                <Skeleton key={index} className="h-11 w-full rounded-lg" />
              ))}
            </div>
          ) : listError ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <TriangleAlert className="size-6 text-destructive" />
              <p className="text-sm text-destructive">{listError}</p>
            </div>
          ) : apps.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Belum ada aplikasi dalam project ini.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table data-testid="project-apps-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Nama</TableHead>
                    <TableHead>Branch</TableHead>
                    <TableHead>Branch webhook</TableHead>
                    <TableHead>Compose</TableHead>
                    <TableHead>Status</TableHead>
                    {canManage ? <TableHead className="text-right">Aksi</TableHead> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {apps.map((app) => {
                    const status = appStatusStyles[app.status] ?? {
                      label: app.status,
                      className:
                        "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
                    };
                    const webhookBranches =
                      app.webhook_branches && app.webhook_branches.length > 0
                        ? app.webhook_branches
                        : [app.branch];
                    return (
                      <TableRow key={app.id} data-testid="project-app-row">
                        <TableCell className="font-medium">{app.name}</TableCell>
                        <TableCell className="font-mono text-xs">{app.branch}</TableCell>
                        <TableCell>
                          <div
                            className="flex max-w-64 flex-wrap gap-1"
                            data-testid="application-webhook-branches"
                          >
                            {webhookBranches.map((branch) => (
                              <Badge
                                key={branch}
                                variant="secondary"
                                className="font-mono text-[0.7rem]"
                              >
                                {branch}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{app.compose_path}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("gap-1.5", status.className)}>
                            <span className="size-1.5 rounded-full bg-current" />
                            {status.label}
                          </Badge>
                        </TableCell>
                        {canManage ? (
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setBranchesApp(app)}
                              data-testid="application-branches-edit"
                            >
                              <Webhook />
                              Atur branch
                            </Button>
                          </TableCell>
                        ) : null}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <RepositoryConnectionDialog
        key={`repository-${project.id}-${repositoryOpen ? "open" : "closed"}`}
        open={repositoryOpen}
        onOpenChange={setRepositoryOpen}
        project={project}
      />
      <ApplicationBranchesDialog
        key={`branches-${branchesApp?.id ?? "none"}-${branchesApp ? "open" : "closed"}`}
        application={branchesApp}
        open={branchesApp !== null}
        onOpenChange={(open) => {
          if (!open) {
            setBranchesApp(null);
          }
        }}
      />
    </div>
  )
}
