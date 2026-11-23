import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bug,
  CircleCheck,
  Filter,
  Loader2,
  RefreshCw,
  ScanSearch,
  Search,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { triggerImageScan, rescanImage, fetchImageScans } from "@/api/image-scans";
import { fetchProjects } from "@/api/projects";
import { ImageScanDetailDialog } from "@/components/security/image-scan-detail-dialog";
import { ImageScanTable } from "@/components/security/image-scan-table";
import { SecurityPostureCard } from "@/components/security/security-posture-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/hooks/use-permissions";
import { cn } from "@/lib/utils";
import type { ImageScanSummary } from "@/types/image-scan";

type SeverityFilter = "all" | "critical" | "high" | "medium" | "low" | "none" | "unknown";

interface Notice {
  tone: "success" | "error";
  text: string;
}

const severityFilters: { value: SeverityFilter; label: string }[] = [
  { value: "all", label: "Semua severity" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "none", label: "Bersih" },
  { value: "unknown", label: "Unknown" },
];

function SummaryCard({
  title,
  description,
  value,
  icon: Icon,
  iconClassName,
  valueClassName,
  loading,
}: {
  title: string;
  description: string;
  value: number;
  icon: typeof Bug;
  iconClassName: string;
  valueClassName: string;
  loading: boolean;
}) {
  return (
    <Card size="sm">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={cn("size-4", iconClassName)} />
      </CardHeader>
      <CardContent className="space-y-1">
        {loading ? (
          <Skeleton className="h-7 w-12" />
        ) : (
          <p className={cn("text-2xl font-semibold tabular-nums", valueClassName)}>{value}</p>
        )}
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

export function SecurityPage() {
  const { canDeploy } = usePermissions();
  const queryClient = useQueryClient();

  const [imageName, setImageName] = useState("");
  const [projectId, setProjectId] = useState("none");
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);

  const scansQuery = useQuery({
    queryKey: ["image-scans"],
    queryFn: () => fetchImageScans({ limit: 100 }),
    refetchInterval: 20_000,
    retry: 1,
  });

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
    retry: 1,
  });

  const scanMutation = useMutation({
    mutationFn: triggerImageScan,
    onSuccess: (scan) => {
      void queryClient.invalidateQueries({ queryKey: ["image-scans"] });
      setDetailId(scan.id);
      setImageName("");
      if (scan.status === "failed") {
        setNotice({
          tone: "error",
          text: scan.error_message ?? "Pemindaian gagal dijalankan.",
        });
      } else {
        setNotice({
          tone: "success",
          text: `Pemindaian ${scan.image_name} selesai: ${scan.critical_count} critical, ${scan.high_count} high.`,
        });
      }
    },
    onError: (error) => {
      setNotice({
        tone: "error",
        text: error instanceof ApiError ? error.message : "Gagal memulai pemindaian.",
      });
    },
  });

  const rescanMutation = useMutation({
    mutationFn: rescanImage,
    onSuccess: (scan) => {
      void queryClient.invalidateQueries({ queryKey: ["image-scans"] });
      setDetailId(scan.id);
      if (scan.status === "failed") {
        setNotice({
          tone: "error",
          text: scan.error_message ?? "Pemindaian ulang gagal dijalankan.",
        });
      } else {
        setNotice({
          tone: "success",
          text: `Pemindaian ulang ${scan.image_name} selesai.`,
        });
      }
    },
    onError: (error) => {
      setNotice({
        tone: "error",
        text: error instanceof ApiError ? error.message : "Gagal memindai ulang image.",
      });
    },
  });

  const scans = useMemo(() => scansQuery.data?.items ?? [], [scansQuery.data]);
  const total = scansQuery.data?.total ?? 0;
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);

  const projectNames = useMemo(
    () => new Map(projects.map((project) => [project.id, project.name])),
    [projects],
  );

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return scans.filter((scan) => {
      const severity = scan.overall_severity ?? "unknown";
      if (severityFilter !== "all" && severity !== severityFilter) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      return (
        scan.image_name.toLowerCase().includes(keyword) ||
        (scan.requested_by ?? "").toLowerCase().includes(keyword) ||
        (scan.project_id !== null &&
          (projectNames.get(scan.project_id) ?? "").toLowerCase().includes(keyword))
      );
    });
  }, [projectNames, scans, search, severityFilter]);

  const totals = useMemo(
    () =>
      scans.reduce(
        (accumulator, scan) => ({
          critical: accumulator.critical + scan.critical_count,
          high: accumulator.high + scan.high_count,
          medium: accumulator.medium + scan.medium_count,
          low: accumulator.low + scan.low_count,
        }),
        { critical: 0, high: 0, medium: 0, low: 0 },
      ),
    [scans],
  );

  const listError = scansQuery.error
    ? scansQuery.error instanceof ApiError
      ? scansQuery.error.message
      : "Tidak dapat memuat riwayat pemindaian."
    : null;

  const rescanningId = rescanMutation.isPending
    ? (rescanMutation.variables ?? null)
    : null;

  const canSubmit = canDeploy && imageName.trim().length > 0 && !scanMutation.isPending;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    scanMutation.mutate({
      image_name: imageName.trim(),
      project_id: projectId === "none" ? undefined : Number(projectId),
    });
  }

  function handleRescan(scanId: number) {
    rescanMutation.mutate(scanId);
  }

  return (
    <div className="space-y-6" data-testid="security-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <ShieldAlert className="size-6 text-indigo-500" />
            Keamanan Container
          </h1>
          <p className="text-sm text-muted-foreground">
            Pindai image container dengan Trivy, telusuri CVE, dan tinjau riwayat temuan.
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
          Auto-refresh 20 detik
        </Badge>
      </div>

      {notice ? (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
            notice.tone === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
          )}
          data-testid="security-notice"
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

      <SecurityPostureCard />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Critical"
          description={`Akumulasi ${scans.length} scan terbaru`}
          value={totals.critical}
          icon={ShieldAlert}
          iconClassName="text-red-500"
          valueClassName="text-red-600 dark:text-red-400"
          loading={scansQuery.isPending}
        />
        <SummaryCard
          title="High"
          description={`Akumulasi ${scans.length} scan terbaru`}
          value={totals.high}
          icon={Bug}
          iconClassName="text-orange-500"
          valueClassName="text-orange-600 dark:text-orange-400"
          loading={scansQuery.isPending}
        />
        <SummaryCard
          title="Medium"
          description={`Akumulasi ${scans.length} scan terbaru`}
          value={totals.medium}
          icon={Bug}
          iconClassName="text-amber-500"
          valueClassName="text-amber-600 dark:text-amber-400"
          loading={scansQuery.isPending}
        />
        <SummaryCard
          title="Low"
          description={`Akumulasi ${scans.length} scan terbaru`}
          value={totals.low}
          icon={ShieldCheck}
          iconClassName="text-sky-500"
          valueClassName="text-sky-600 dark:text-sky-400"
          loading={scansQuery.isPending}
        />
      </div>

      <Card data-testid="image-scan-trigger-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ScanSearch className="size-4 text-muted-foreground" />
            Pindai image baru
          </CardTitle>
          <CardDescription>
            Pemindaian dijalankan sinkron memakai Trivy. Image publik diambil dari registry;
            image privat memerlukan kredensial registry di host backend.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 lg:flex-row lg:items-end">
            <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(0,1fr)_220px]">
              <div className="space-y-1.5">
                <Label htmlFor="image-name">Referensi image</Label>
                <Input
                  id="image-name"
                  value={imageName}
                  onChange={(event) => setImageName(event.target.value)}
                  placeholder="nginx:1.27 atau ghcr.io/org/app:tag"
                  className="font-mono text-xs"
                  disabled={!canDeploy || scanMutation.isPending}
                  data-testid="image-scan-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="image-scan-project">Project (opsional)</Label>
                <Select
                  value={projectId}
                  onValueChange={setProjectId}
                  disabled={!canDeploy || projectsQuery.isPending}
                >
                  <SelectTrigger id="image-scan-project" className="w-full">
                    <SelectValue placeholder="Tanpa project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Tanpa project</SelectItem>
                    {projects.map((project) => (
                      <SelectItem key={project.id} value={String(project.id)}>
                        {project.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button
              type="submit"
              disabled={!canSubmit}
              className="lg:mb-0"
              data-testid="image-scan-submit"
            >
              {scanMutation.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <ScanSearch />
              )}
              {scanMutation.isPending ? "Memindai..." : "Pindai image"}
            </Button>
          </form>
          {!canDeploy ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Peran Viewer hanya dapat melihat riwayat dan detail temuan.
            </p>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              Batas waktu pemindaian dan threshold alert diatur melalui environment backend
              (TRIVY_PATH, IMAGE_SCAN_TIMEOUT_SECONDS, IMAGE_SCAN_CRITICAL_THRESHOLD).
            </p>
          )}
        </CardContent>
      </Card>

      <Card size="sm">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Cari image, project, atau pemindai"
              className="w-[280px] pl-8"
              aria-label="Cari riwayat pemindaian"
              data-testid="image-scan-search"
            />
          </div>
          <Select
            value={severityFilter}
            onValueChange={(value) => setSeverityFilter(value as SeverityFilter)}
          >
            <SelectTrigger className="w-[170px]" aria-label="Filter severity">
              <Filter className="size-3.5" />
              <SelectValue placeholder="Severity" />
            </SelectTrigger>
            <SelectContent>
              {severityFilters.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground" data-testid="image-scan-count">
            {filtered.length} dari {scans.length} scan ditampilkan
            {total > scans.length ? ` · total ${total}` : ""}
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Riwayat pemindaian</CardTitle>
            <CardDescription>
              Setiap rescan membuat baris baru agar perubahan temuan dapat dibandingkan.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {scansQuery.isPending ? (
            <div className="space-y-2">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-14 w-full rounded-lg" />
              ))}
            </div>
          ) : listError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <TriangleAlert className="size-6 text-destructive" />
              <p className="text-sm text-destructive">{listError}</p>
              <Button variant="outline" size="sm" onClick={() => void scansQuery.refetch()}>
                Coba lagi
              </Button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <ShieldCheck className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">
                {scans.length === 0
                  ? "Belum ada pemindaian image"
                  : "Tidak ada scan yang cocok"}
              </p>
              <p className="max-w-md text-xs text-muted-foreground">
                {scans.length === 0
                  ? "Masukkan referensi image di atas untuk mulai memindai kerentanan."
                  : "Ubah kata kunci atau filter severity untuk melihat scan lain."}
              </p>
            </div>
          ) : (
            <ImageScanTable
              scans={filtered}
              projectNames={projectNames}
              rescanningId={rescanningId}
              canScan={canDeploy}
              onSelect={(scan: ImageScanSummary) => setDetailId(scan.id)}
              onRescan={(scan: ImageScanSummary) => handleRescan(scan.id)}
            />
          )}
        </CardContent>
      </Card>

      <ImageScanDetailDialog
        scanId={detailId}
        open={detailId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDetailId(null);
          }
        }}
        canScan={canDeploy}
        isRescanning={rescanMutation.isPending}
        onRescan={handleRescan}
      />

      <div className="flex items-center justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={() => void scansQuery.refetch()}
          disabled={scansQuery.isFetching}
        >
          <RefreshCw className={cn("size-3.5", scansQuery.isFetching && "animate-spin")} />
          Muat ulang
        </Button>
      </div>
    </div>
  );
}
