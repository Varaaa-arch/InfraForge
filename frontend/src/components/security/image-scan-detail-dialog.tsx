import { useQuery } from "@tanstack/react-query";
import {
  ExternalLink,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { fetchImageScan } from "@/api/image-scans";
import { SeverityBadge } from "@/components/security/severity-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function safeUrl(value: string | null): string | null {
  if (!value || !/^https?:\/\//i.test(value)) {
    return null;
  }
  return value;
}

function CountCard({
  label,
  value,
  className,
}: {
  label: string;
  value: number;
  className: string;
}) {
  return (
    <div className={cn("rounded-lg border px-3 py-2", className)}>
      <p className="text-[11px] font-medium tracking-wide uppercase opacity-80">{label}</p>
      <p className="text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

interface ImageScanDetailDialogProps {
  scanId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canScan: boolean;
  isRescanning: boolean;
  onRescan: (scanId: number) => void;
}

export function ImageScanDetailDialog({
  scanId,
  open,
  onOpenChange,
  canScan,
  isRescanning,
  onRescan,
}: ImageScanDetailDialogProps) {
  const scanQuery = useQuery({
    queryKey: ["image-scans", scanId],
    queryFn: () => fetchImageScan(scanId as number),
    enabled: open && scanId !== null,
    retry: 1,
  });

  const scan = scanQuery.data;
  const error = scanQuery.error
    ? scanQuery.error instanceof ApiError
      ? scanQuery.error.message
      : "Tidak dapat memuat detail scan."
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl" data-testid="image-scan-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="size-4 text-muted-foreground" />
            Detail pemindaian
          </DialogTitle>
          <DialogDescription>
            Ringkasan kerentanan image dan daftar CVE yang ditemukan Trivy.
          </DialogDescription>
        </DialogHeader>

        {scanQuery.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-48 w-full rounded-lg" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void scanQuery.refetch()}>
              Coba lagi
            </Button>
          </div>
        ) : scan ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2.5">
              <div className="min-w-0 space-y-1">
                <p className="truncate font-mono text-sm font-medium">{scan.image_name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {scan.image_digest ?? "Digest tidak tersedia"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Dipindai {formatDate(scan.scanned_at)} oleh {scan.requested_by ?? "sistem"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <SeverityBadge severity={scan.overall_severity} />
                <Badge variant="outline" className="capitalize">
                  {scan.status}
                </Badge>
                <Badge variant="secondary">{scan.total_count} temuan</Badge>
              </div>
            </div>

            {scan.error_message ? (
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                <p className="whitespace-pre-wrap break-words">{scan.error_message}</p>
              </div>
            ) : null}

            <div className="grid gap-2 sm:grid-cols-4">
              <CountCard
                label="Critical"
                value={scan.critical_count}
                className="border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
              />
              <CountCard
                label="High"
                value={scan.high_count}
                className="border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400"
              />
              <CountCard
                label="Medium"
                value={scan.medium_count}
                className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
              />
              <CountCard
                label="Low"
                value={scan.low_count}
                className="border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400"
              />
            </div>

            <div className="max-h-[42vh] overflow-auto rounded-lg border">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card">
                  <TableRow>
                    <TableHead>CVE</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Package</TableHead>
                    <TableHead>Terpasang</TableHead>
                    <TableHead>Perbaikan</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scan.findings.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <div className="flex flex-col items-center gap-1 py-6 text-center">
                          {scan.status === "completed" ? (
                            <ShieldCheck className="size-5 text-emerald-500" />
                          ) : (
                            <ShieldAlert className="size-5 text-muted-foreground" />
                          )}
                          <p className="text-sm font-medium">
                            {scan.status === "completed"
                              ? "Tidak ada temuan CVE tersimpan"
                              : "Belum ada hasil pemindaian"}
                          </p>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    scan.findings.map((finding, index) => {
                      const url = safeUrl(finding.primary_url);
                      return (
                        <TableRow key={`${finding.cve_id}-${finding.package}-${index}`}>
                          <TableCell className="max-w-[220px] whitespace-normal">
                            <div className="flex items-start gap-1">
                              <span className="font-mono text-xs font-medium">
                                {finding.cve_id}
                              </span>
                              {url ? (
                                <a
                                  href={url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-muted-foreground hover:text-foreground"
                                  aria-label={`Buka referensi ${finding.cve_id}`}
                                >
                                  <ExternalLink className="size-3" />
                                </a>
                              ) : null}
                            </div>
                            {finding.title ? (
                              <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                                {finding.title}
                              </p>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            <SeverityBadge severity={finding.severity} />
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {finding.package}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {finding.installed_version ?? "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {finding.fixed_version ?? "Belum tersedia"}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>

            {scan.findings.length < scan.total_count ? (
              <p className="text-xs text-muted-foreground">
                Menampilkan {scan.findings.length} dari {scan.total_count} temuan
                (batas penyimpanan finding per scan).
              </p>
            ) : null}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Tutup
          </Button>
          {canScan && scanId !== null ? (
            <Button
              onClick={() => onRescan(scanId)}
              disabled={isRescanning}
              data-testid="image-scan-detail-rescan"
            >
              {isRescanning ? (
                <Loader2 className="animate-spin" />
              ) : (
                <RefreshCw />
              )}
              Pindai ulang
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
