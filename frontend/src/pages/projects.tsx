import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FolderKanban, GitBranch, GitFork, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { fetchApplications, fetchProjects } from "@/api/projects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Project } from "@/types/project";

const timeFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
});

function ProjectCard({
  project,
  applicationCount,
}: {
  project: Project;
  applicationCount: number;
}) {
  return (
    <Card className="flex flex-col" data-testid="project-card">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <FolderKanban className="size-4 text-muted-foreground" />
              {project.name}
            </CardTitle>
            <CardDescription>
              {project.description ?? `Slug: ${project.slug}`}
            </CardDescription>
          </div>
          <Badge
            variant="outline"
            className={cn(
              "shrink-0",
              project.visibility === "public"
                ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400"
                : "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
            )}
          >
            {project.visibility === "public" ? "Public" : "Private"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-2 text-sm">
        <div className="flex items-start gap-2">
          <GitFork className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate font-mono text-xs">
            {project.repository_url ?? "Belum terhubung ke repository"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <GitBranch className="size-3.5" />
            {project.default_branch ?? "-"}
          </span>
          <span>{applicationCount} aplikasi</span>
          <span>Diperbarui {timeFormatter.format(new Date(project.updated_at))}</span>
        </div>
      </CardContent>

      <CardFooter>
        <Button asChild variant="outline" size="sm" className="w-full justify-between">
          <Link to={`/projects/${project.id}`}>
            Buka project
            <ArrowRight className="size-3.5" />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}

export function ProjectsPage() {
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
    refetchInterval: 30_000,
    retry: 1,
  });

  const applicationsQuery = useQuery({
    queryKey: ["applications"],
    queryFn: fetchApplications,
    refetchInterval: 30_000,
    retry: 1,
  });

  const projects = projectsQuery.data ?? [];

  const applicationCountByProject = useMemo(() => {
    const counts = new Map<number, number>();
    for (const application of applicationsQuery.data ?? []) {
      counts.set(application.project_id, (counts.get(application.project_id) ?? 0) + 1);
    }
    return counts;
  }, [applicationsQuery.data]);

  const listError = projectsQuery.error
    ? projectsQuery.error instanceof ApiError
      ? projectsQuery.error.message
      : "Tidak dapat memuat daftar project."
    : null;

  return (
    <div className="space-y-6" data-testid="projects-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Project mengelompokkan aplikasi beserta environment variable yang dipakai bersama.
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

      {projectsQuery.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} className="h-[220px] w-full rounded-xl" />
          ))}
        </div>
      ) : listError ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{listError}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void projectsQuery.refetch()}
            >
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <FolderKanban className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada project</p>
            <p className="max-w-md text-xs text-muted-foreground">
              Project mengelompokkan aplikasi beserta environment variable yang dipakai bersama.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              applicationCount={applicationCountByProject.get(project.id) ?? 0}
            />
          ))}
        </div>
      )}
    </div>
  )
}
