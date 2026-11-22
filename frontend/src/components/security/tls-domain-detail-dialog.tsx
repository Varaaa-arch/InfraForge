import { useQuery } from "@tanstack/react-query";
import { Loader2, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";

import { ApiError } from "@/api/client";
import { fetchTlsDomain } from "@/api/tls-domains";
import { TlsStatusBadge } from "@/components/security/tls-status-badge";
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

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function InfoItem({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
      <p className="truncate text-sm">{value ?? "—"}</p>
    </div>
  );
}

interface TlsDomainDetailDialogProps {
  domainId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canManage: boolean;
  isChecking: boolean;
  onCheck: (domainId: number) => void;
}

export function TlsDomainDetailDialog({
  domainId,
  open,
  onOpenChange,
  canManage,
  isChecking,
  onCheck,
}: TlsDomainDetailDialogProps) {
  const domainQuery = useQuery({
    queryKey: ["tls-domains", domainId],
    queryFn: () => fetchTlsDomain(domainId as number),
    enabled: open && domainId !== null,
    retry: 1,
  });

  const domain = domainQuery.data;
  const error = domainQuery.error
    ? domainQuery.error instanceof ApiError
      ? domainQuery.error.message
      : "Tidak dapat memuat detail target TLS."
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl" data-testid="tls-domain-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-muted-foreground" />
            Detail sertifikat
          </DialogTitle>
          <DialogDescription>
            Metadata sertifikat terakhir dan riwayat pemeriksaan TLS.
          </DialogDescription>
        </DialogHeader>

        {domainQuery.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void domainQuery.refetch()}>
              Coba lagi
            </Button>
          </div>
        ) : domain ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2.5">
              <div className="min-w-0 space-y-1">
                <p className="truncate font-mono text-sm font-medium">
                  {domain.host}:{domain.port}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {domain.name ?? "Tanpa label"} · warning {domain.warning_days} hari
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <TlsStatusBadge status={domain.status} />
                {domain.trusted ? (
                  <Badge
                    variant="outline"
                    className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  >
                    Terpercaya
                  </Badge>
                ) : (
                  <Badge variant="secondary">Tidak terverifikasi</Badge>
                )}
                {domain.enabled ? null : <Badge variant="secondary">Nonaktif</Badge>}
              </div>
            </div>

            {domain.error_message ? (
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                <p className="whitespace-pre-wrap break-words">{domain.error_message}</p>
              </div>
            ) : null}

            <div className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2 lg:grid-cols-4">
              <InfoItem
                label="Kedaluwarsa"
                value={formatDate(domain.expiry_date)}
              />
              <InfoItem
                label="Sisa hari"
                value={
                  domain.days_remaining === null ? null : `${domain.days_remaining} hari`
                }
              />
              <InfoItem label="Protocol" value={domain.protocol} />
              <InfoItem label="Terakhir dicek" value={formatDate(domain.last_checked_at)} />
              <InfoItem label="Issuer" value={domain.issuer} />
              <InfoItem label="Subject" value={domain.subject} />
              <InfoItem label="Dibuat oleh" value={domain.created_by} />
              <InfoItem label="Ditambahkan" value={formatDate(domain.created_at)} />
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">Riwayat pemeriksaan</p>
              {domain.checks.length === 0 ? (
                <p className="rounded-lg border px-3 py-6 text-center text-xs text-muted-foreground">
                  Belum ada pemeriksaan. Klik “Periksa ulang” untuk memulai.
                </p>
              ) : (
                <div className="max-h-[36vh] overflow-auto rounded-lg border">
                  <Table>
                    <TableHeader className="sticky top-0 z-10 bg-card">
                      <TableRow>
                        <TableHead>Waktu</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Sisa hari</TableHead>
                        <TableHead>Protocol</TableHead>
                        <TableHead>Alert</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {domain.checks.map((check) => (
                        <TableRow key={check.id}>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDate(check.checked_at)}
                          </TableCell>
                          <TableCell>
                            <TlsStatusBadge status={check.status} />
                          </TableCell>
                          <TableCell className="text-xs tabular-nums">
                            {check.days_remaining ?? "—"}
                          </TableCell>
                          <TableCell className="text-xs">{check.protocol ?? "—"}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {check.alert_sent ? "Terkirim" : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Tutup
          </Button>
          {canManage && domainId !== null ? (
            <Button
              onClick={() => onCheck(domainId)}
              disabled={isChecking}
              data-testid="tls-domain-detail-check"
            >
              {isChecking ? (
                <Loader2 className="animate-spin" />
              ) : (
                <RefreshCw />
              )}
              Periksa ulang
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
