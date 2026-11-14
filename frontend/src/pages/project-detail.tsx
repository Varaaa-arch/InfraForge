import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FolderKanban, TriangleAlert } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { fetchProject } from "@/api/projects";
import { EnvVarsPanel } from "@/components/projects/env-vars-panel";
import { ProjectSummary } from "@/components/projects/project-summary";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type ProjectTab = "summary" | "env";

export function ProjectDetailPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const [searchParams, setSearchParams] = useSearchParams();

  const tab: ProjectTab = searchParams.get("tab") === "env" ? "env" : "summary";

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
    enabled: Number.isFinite(projectId),
    retry: 1,
  });

  const project = projectQuery.data;

  const listError = projectQuery.error
    ? projectQuery.error instanceof ApiError
      ? projectQuery.error.message
      : "Tidak dapat memuat detail project."
    : null;

  function setTab(next: ProjectTab) {
    setSearchParams(
      (previous) => {
        const params = new URLSearchParams(previous);
        if (next === "env") {
          params.set("tab", "env");
        } else {
          params.delete("tab");
        }
        return params;
      },
      { replace: true },
    );
  }

  if (projectQuery.isPending) {
    return (
      <div className="space-y-4" data-testid="project-detail-page">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (listError || !project) {
    return (
      <div className="space-y-4" data-testid="project-detail-page">
        <Button asChild variant="ghost" size="sm" className="w-fit">
          <Link to="/projects">
            <ArrowLeft className="size-3.5" />
            Kembali ke projects
          </Link>
        </Button>
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">
              {listError ?? "Project tidak ditemukan."}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="project-detail-page">
      <div className="space-y-3">
        <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit">
          <Link to="/projects">
            <ArrowLeft className="size-3.5" />
            Projects
          </Link>
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <FolderKanban className="size-5 text-muted-foreground" />
              <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
              <Badge
                variant="outline"
                className={cn(
                  project.visibility === "public"
                    ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400"
                    : "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
                )}
              >
                {project.visibility === "public" ? "Public" : "Private"}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {project.description ?? `Slug: ${project.slug}`}
            </p>
          </div>
        </div>

        <div
          className="inline-flex items-center gap-1 rounded-lg border bg-muted/40 p-1"
          role="tablist"
          aria-label="Bagian project"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === "summary"}
            onClick={() => setTab("summary")}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === "summary"
                ? "bg-background font-medium text-foreground shadow-sm ring-1 ring-foreground/10"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            Ringkasan
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "env"}
            onClick={() => setTab("env")}
            data-testid="tab-env"
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab === "env"
                ? "bg-background font-medium text-foreground shadow-sm ring-1 ring-foreground/10"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            Environment Variables
          </button>
        </div>
      </div>

      {tab === "summary" ? (
        <ProjectSummary project={project} />
      ) : (
        <EnvVarsPanel projectId={project.id} />
      )}
    </div>
  )
}
