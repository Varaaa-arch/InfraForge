import { Loader2Icon, RefreshCw, Search } from "lucide-react";

import { SeverityBadge } from "@/components/security/severity-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { ImageScanSummary } from "@/types/image-scan";

const statusStyles: Record<string, { label: string; className: string }> = {
  pending: {
    label: "Menunggu",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
  running: {
    label: "Memindai",
    className: "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  },
  completed: {
    label: "Selesai",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  failed: {
    label: "Gagal",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function CountBadge({ label, value, className }: { label: string; value: number; className: string }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-6 items-center justify-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium tabular-nums",
        className,
      )}
      title={`${value} ${label}`}
    >
      {label} {value}
    </span>
  );
}

interface ImageScanTableProps {
  scans: ImageScanSummary[];
  projectNames: Map<number, string>;
  rescanningId: number | null;
  canScan: boolean;
  onSelect: (scan: ImageScanSummary) => void;
  onRescan: (scan: ImageScanSummary) => void;
}

export function ImageScanTable({
  scans,
  projectNames,
  rescanningId,
  canScan,
  onSelect,
  onRescan,
}: ImageScanTableProps) {
  return (
    <div className="overflow-x-auto">
      <Table data-testid="image-scan-table">
        <TableHeader>
          <TableRow>
            <TableHead>Image</TableHead>
            <TableHead>Project</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Severity</TableHead>
            <TableHead>Temuan</TableHead>
            <TableHead>Waktu</TableHead>
            <TableHead className="text-right">Aksi</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {scans.map((scan) => {
            const status = statusStyles[scan.status] ?? {
              label: scan.status,
              className:
                "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
            };
            const busy = rescanningId === scan.id;

            return (
              <TableRow key={scan.id} data-testid="image-scan-row">
                <TableCell className="max-w-[260px] whitespace-normal">
                  <span className="block truncate font-mono text-xs font-medium">
                    {scan.image_name}
                  </span>
                  {scan.image_digest ? (
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {scan.image_digest}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell>
                  {scan.project_id === null ? (
                    <span className="text-xs text-muted-foreground">Tanpa project</span>
                  ) : (
                    <Badge variant="secondary" className="text-[10px]">
                      {projectNames.get(scan.project_id) ?? `#${scan.project_id}`}
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={cn("gap-1.5", status.className)}
                    data-testid="image-scan-status"
                  >
                    <span className="size-1.5 rounded-full bg-current" />
                    {status.label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <SeverityBadge severity={scan.overall_severity} />
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    <CountBadge
                      label="C"
                      value={scan.critical_count}
                      className="border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
                    />
                    <CountBadge
                      label="H"
                      value={scan.high_count}
                      className="border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400"
                    />
                    <CountBadge
                      label="M"
                      value={scan.medium_count}
                      className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                    />
                    <CountBadge
                      label="L"
                      value={scan.low_count}
                      className="border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400"
                    />
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDate(scan.scanned_at ?? scan.created_at)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {busy ? (
                      <Loader2Icon className="size-4 animate-spin text-muted-foreground" />
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Lihat detail CVE"
                      aria-label={`Lihat detail ${scan.image_name}`}
                      onClick={() => onSelect(scan)}
                      data-testid="image-scan-detail"
                    >
                      <Search />
                    </Button>
                    {canScan ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Pindai ulang"
                        aria-label={`Pindai ulang ${scan.image_name}`}
                        disabled={busy}
                        onClick={() => onRescan(scan)}
                        data-testid="image-scan-rescan"
                      >
                        <RefreshCw className={cn(busy && "animate-spin")} />
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
