import {
  Eye,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { TlsStatusBadge } from "@/components/security/tls-status-badge";
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
import type { TlsDomainSummary } from "@/types/tls-domain";

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function expiryLabel(domain: TlsDomainSummary): string {
  if (!domain.expiry_date) {
    return "—";
  }
  if (domain.days_remaining === null) {
    return formatDate(domain.expiry_date);
  }
  if (domain.days_remaining < 0) {
    return `${Math.abs(domain.days_remaining)} hari lalu`;
  }
  if (domain.days_remaining === 0) {
    return "Hari ini";
  }
  return `${domain.days_remaining} hari lagi`;
}

interface TlsDomainTableProps {
  domains: TlsDomainSummary[];
  checkingId: number | null;
  canManage: boolean;
  onDetail: (domain: TlsDomainSummary) => void;
  onCheck: (domain: TlsDomainSummary) => void;
  onEdit: (domain: TlsDomainSummary) => void;
  onDelete: (domain: TlsDomainSummary) => void;
}

export function TlsDomainTable({
  domains,
  checkingId,
  canManage,
  onDetail,
  onCheck,
  onEdit,
  onDelete,
}: TlsDomainTableProps) {
  return (
    <div className="overflow-x-auto">
      <Table data-testid="tls-domain-table">
        <TableHeader>
          <TableRow>
            <TableHead>Target</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Kedaluwarsa</TableHead>
            <TableHead>Issuer</TableHead>
            <TableHead>Terakhir dicek</TableHead>
            <TableHead className="text-right">Aksi</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {domains.map((domain) => {
            const busy = checkingId === domain.id;
            return (
              <TableRow key={domain.id} data-testid="tls-domain-row">
                <TableCell className="max-w-[280px] whitespace-normal">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-mono text-xs font-medium">
                      {domain.host}:{domain.port}
                    </span>
                    {domain.enabled ? null : (
                      <Badge variant="secondary" className="text-[10px]">
                        Nonaktif
                      </Badge>
                    )}
                  </div>
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                    {domain.name ?? "Tanpa label"}
                    {domain.protocol ? ` · ${domain.protocol}` : ""}
                  </span>
                </TableCell>
                <TableCell>
                  <TlsStatusBadge status={domain.status} />
                  {domain.error_message ? (
                    <p className="mt-1 line-clamp-2 max-w-[220px] text-[11px] text-muted-foreground">
                      {domain.error_message}
                    </p>
                  ) : null}
                </TableCell>
                <TableCell>
                  <span className="text-xs">{expiryLabel(domain)}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    {formatDate(domain.expiry_date)}
                  </span>
                </TableCell>
                <TableCell className="max-w-[180px] truncate text-xs text-muted-foreground">
                  {domain.issuer ?? "—"}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDate(domain.last_checked_at)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {busy ? (
                      <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Lihat detail"
                      aria-label={`Lihat detail ${domain.host}`}
                      onClick={() => onDetail(domain)}
                      data-testid="tls-domain-detail"
                    >
                      <Eye />
                    </Button>
                    {canManage ? (
                      <>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Periksa ulang"
                          aria-label={`Periksa ulang ${domain.host}`}
                          onClick={() => onCheck(domain)}
                          disabled={busy}
                          data-testid="tls-domain-check"
                        >
                          <RefreshCw className={busy ? "animate-spin" : undefined} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Ubah target"
                          aria-label={`Ubah ${domain.host}`}
                          onClick={() => onEdit(domain)}
                          data-testid="tls-domain-edit"
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Hapus target"
                          aria-label={`Hapus ${domain.host}`}
                          className="text-destructive hover:text-destructive"
                          onClick={() => onDelete(domain)}
                          data-testid="tls-domain-delete"
                        >
                          <Trash2 />
                        </Button>
                      </>
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
