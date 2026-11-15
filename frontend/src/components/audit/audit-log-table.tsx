import { Eye } from "lucide-react";

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
import type { AuditLogEntry } from "@/types/audit-log";

const dateFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "medium",
});

function formatDateTime(iso: string): string {
  return dateFormatter.format(new Date(iso));
}

function formatRelative(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) {
    return "baru saja";
  }
  if (minutes < 60) {
    return `${minutes} menit lalu`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} jam lalu`;
  }
  return `${Math.round(hours / 24)} hari lalu`;
}

function statusClassName(status: number): string {
  if (status >= 500) {
    return "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400";
  }
  if (status >= 400) {
    return "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400";
  }
  if (status >= 200 && status < 300) {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  }
  return "border-border text-muted-foreground";
}

export function AuditLogTable({
  items,
  onSelect,
}: {
  items: AuditLogEntry[];
  onSelect: (entry: AuditLogEntry) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="px-3">Waktu</TableHead>
            <TableHead className="px-3">User</TableHead>
            <TableHead className="px-3">Aksi</TableHead>
            <TableHead className="hidden px-3 md:table-cell">Resource</TableHead>
            <TableHead className="px-3">Status</TableHead>
            <TableHead className="hidden px-3 lg:table-cell">IP</TableHead>
            <TableHead className="w-12 px-3 text-right">
              <span className="sr-only">Detail</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((entry) => (
            <TableRow
              key={entry.id}
              data-testid="audit-row"
              className="cursor-pointer"
              onClick={() => onSelect(entry)}
            >
              <TableCell className="px-3">
                <span
                  className="text-xs text-muted-foreground"
                  title={formatDateTime(entry.created_at)}
                >
                  {formatRelative(entry.created_at)}
                </span>
              </TableCell>
              <TableCell className="px-3">
                <span className="font-mono text-xs">
                  {entry.username ?? "—"}
                </span>
              </TableCell>
              <TableCell className="px-3">
                <Badge variant="outline" className="font-mono text-[0.65rem]">
                  {entry.action}
                </Badge>
              </TableCell>
              <TableCell className="hidden px-3 md:table-cell">
                <span className="text-xs text-muted-foreground">
                  {entry.resource_type ?? "—"}
                  {entry.resource_id ? (
                    <span className="font-mono"> #{entry.resource_id}</span>
                  ) : null}
                </span>
              </TableCell>
              <TableCell className="px-3">
                <Badge
                  variant="outline"
                  className={cn(
                    "font-mono text-[0.65rem]",
                    statusClassName(entry.status_code),
                  )}
                >
                  {entry.status_code}
                </Badge>
              </TableCell>
              <TableCell className="hidden px-3 lg:table-cell">
                <span className="font-mono text-xs text-muted-foreground">
                  {entry.ip_address ?? "—"}
                </span>
              </TableCell>
              <TableCell className="px-3 text-right">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Lihat detail audit"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(entry);
                  }}
                >
                  <Eye className="size-3.5" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
