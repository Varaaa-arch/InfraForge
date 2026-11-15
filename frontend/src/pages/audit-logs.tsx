import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";
import { useState } from "react";

import { fetchAuditFilterMeta, fetchAuditLogs } from "@/api/audit-logs";
import { ApiError } from "@/api/client";
import { AuditFilters } from "@/components/audit/audit-filters";
import { AuditLogTable } from "@/components/audit/audit-log-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { AuditLogEntry } from "@/types/audit-log";

const dateFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "full",
  timeStyle: "medium",
});

function toIso(value: string): string | undefined {
  if (!value) {
    return undefined;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words">{value}</span>
    </div>
  );
}

function AuditDetailDialog({
  entry,
  onClose,
}: {
  entry: AuditLogEntry | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={entry !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="audit-detail-dialog">
        <DialogHeader>
          <DialogTitle className="font-mono">{entry?.action}</DialogTitle>
          <DialogDescription>
            Detail aktivitas audit #{entry?.id ?? "—"}
          </DialogDescription>
        </DialogHeader>

        {entry ? (
          <div className="space-y-3">
            <DetailRow
              label="Waktu"
              value={dateFormatter.format(new Date(entry.created_at))}
            />
            <DetailRow label="User" value={entry.username ?? "—"} />
            <DetailRow
              label="Request"
              value={
                <span className="font-mono text-xs">
                  {entry.method} {entry.path}
                </span>
              }
            />
            <DetailRow
              label="Resource"
              value={
                entry.resource_type ? (
                  <span className="font-mono text-xs">
                    {entry.resource_type}
                    {entry.resource_id ? ` #${entry.resource_id}` : ""}
                  </span>
                ) : (
                  "—"
                )
              }
            />
            <DetailRow label="Status" value={`HTTP ${entry.status_code}`} />
            <DetailRow
              label="IP"
              value={<span className="font-mono text-xs">{entry.ip_address ?? "—"}</span>}
            />
            <DetailRow
              label="User agent"
              value={
                <span className="text-xs text-muted-foreground">
                  {entry.user_agent ?? "—"}
                </span>
              }
            />
            <DetailRow
              label="Detail"
              value={
                entry.details && Object.keys(entry.details).length > 0 ? (
                  <pre className="max-h-48 overflow-auto rounded-md bg-muted/50 p-2 font-mono text-xs">
                    {JSON.stringify(entry.details, null, 2)}
                  </pre>
                ) : (
                  "—"
                )
              }
            />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

export function AuditLogsPage() {
  const [username, setUsername] = useState("all");
  const [action, setAction] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<AuditLogEntry | null>(null);

  const metaQuery = useQuery({
    queryKey: ["audit-logs", "filters"],
    queryFn: fetchAuditFilterMeta,
  });

  const query = useQuery({
    queryKey: [
      "audit-logs",
      "list",
      { username, action, dateFrom, dateTo, limit, offset },
    ],
    queryFn: () =>
      fetchAuditLogs({
        username: username === "all" ? undefined : username,
        action: action === "all" ? undefined : action,
        from: toIso(dateFrom),
        to: toIso(dateTo),
        limit,
        offset,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  const isAdmin = metaQuery.data?.is_admin ?? false;
  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const errorMessage = query.error
    ? query.error instanceof ApiError
      ? query.error.message
      : "Tidak dapat memuat audit log."
    : null;

  const resetFilters = () => {
    setUsername("all");
    setAction("all");
    setDateFrom("");
    setDateTo("");
    setOffset(0);
  };

  const changeFilter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setOffset(0);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Audit Logs</h1>
          <p className="text-sm text-muted-foreground">
            Riwayat aksi sensitif: deploy, rollback, restart container, perubahan env
            var, dan pengelolaan platform.
          </p>
        </div>
        <Badge variant="outline" className="gap-1.5">
          <ShieldCheck className="size-3.5" />
          {isAdmin ? "Semua aktivitas" : "Aktivitas saya"}
        </Badge>
      </div>

      <AuditFilters
        meta={metaQuery.data}
        username={username}
        action={action}
        dateFrom={dateFrom}
        dateTo={dateTo}
        isFetching={query.isFetching}
        total={total}
        onUsernameChange={changeFilter(setUsername)}
        onActionChange={changeFilter(setAction)}
        onDateFromChange={changeFilter(setDateFrom)}
        onDateToChange={changeFilter(setDateTo)}
        onReset={resetFilters}
        onRefresh={() => void query.refetch()}
      />

      {errorMessage ? (
        <Card>
          <CardContent className="flex items-center gap-3 p-6 text-sm text-muted-foreground">
            <ShieldQuestion className="size-5 text-destructive" />
            {errorMessage}
          </CardContent>
        </Card>
      ) : query.isPending ? (
        <div className="space-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
          {[0, 1, 2, 3, 4].map((index) => (
            <Skeleton key={index} className="h-10 w-full rounded-md" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-10 text-center">
            <ShieldCheck className="size-8 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada aktivitas</p>
            <p className="text-xs text-muted-foreground">
              Aksi mutasi yang Anda (atau tim) lakukan akan muncul di sini.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <AuditLogTable items={items} onSelect={setSelected} />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              Menampilkan {offset + 1}–{Math.min(offset + limit, total)} dari {total}{" "}
              aktivitas
            </p>
            <div className="flex items-center gap-2">
              <Select
                value={String(limit)}
                onValueChange={(value) => {
                  setLimit(Number(value));
                  setOffset(0);
                }}
              >
                <SelectTrigger className="h-8 w-[110px]" aria-label="Jumlah baris">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="25">25 / hal</SelectItem>
                  <SelectItem value="50">50 / hal</SelectItem>
                  <SelectItem value="100">100 / hal</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                data-testid="audit-prev"
              >
                <ChevronLeft className="size-3.5" />
                Sebelumnya
              </Button>
              <span className="text-xs tabular-nums text-muted-foreground">
                {page} / {pageCount}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount}
                onClick={() => setOffset(offset + limit)}
                data-testid="audit-next"
              >
                Berikutnya
                <ChevronRight className="size-3.5" />
              </Button>
            </div>
          </div>
        </div>
      )}

      <AuditDetailDialog entry={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
