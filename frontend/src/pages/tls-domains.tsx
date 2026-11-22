import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  Filter,
  GlobeLock,
  Loader2,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import {
  checkTlsDomain,
  createTlsDomain,
  deleteTlsDomain,
  fetchTlsDomains,
  updateTlsDomain,
} from "@/api/tls-domains";
import { TlsDomainDetailDialog } from "@/components/security/tls-domain-detail-dialog";
import { TlsDomainFormDialog } from "@/components/security/tls-domain-form-dialog";
import { TlsDomainTable } from "@/components/security/tls-domain-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
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
import type {
  TlsDomainCreatePayload,
  TlsDomainStatus,
  TlsDomainSummary,
  TlsDomainUpdatePayload,
} from "@/types/tls-domain";

type StatusFilter = "all" | TlsDomainStatus;

interface Notice {
  tone: "success" | "error";
  text: string;
}

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Semua status" },
  { value: "healthy", label: "Sehat" },
  { value: "expiring", label: "Segera kedaluwarsa" },
  { value: "expired", label: "Kedaluwarsa" },
  { value: "invalid", label: "Tidak valid" },
  { value: "error", label: "Error" },
  { value: "pending", label: "Belum diperiksa" },
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
  icon: typeof GlobeLock;
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
          <p className={cn("text-2xl font-semibold tabular-nums", valueClassName)}>
            {value}
          </p>
        )}
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function TlsDomainsPage() {
  const { canDeploy } = usePermissions();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TlsDomainSummary | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TlsDomainSummary | null>(null);

  const domainsQuery = useQuery({
    queryKey: ["tls-domains"],
    queryFn: () => fetchTlsDomains({ limit: 200 }),
    refetchInterval: 60_000,
    retry: 1,
  });

  const domains = useMemo(() => domainsQuery.data?.items ?? [], [domainsQuery.data]);
  const total = domainsQuery.data?.total ?? 0;

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["tls-domains"] });
  }

  const createMutation = useMutation({
    mutationFn: createTlsDomain,
    onSuccess: (domain) => {
      invalidate();
      setFormOpen(false);
      setEditing(null);
      setFormError(null);
      setNotice({
        tone: domain.status === "healthy" ? "success" : "error",
        text:
          domain.status === "healthy"
            ? `${domain.host}:${domain.port} berhasil ditambahkan dan sertifikat sehat.`
            : `${domain.host}:${domain.port} ditambahkan dengan status ${domain.status}.`,
      });
    },
    onError: (error) => {
      setFormError(errorMessage(error, "Gagal menambahkan target TLS."));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TlsDomainUpdatePayload }) =>
      updateTlsDomain(id, payload),
    onSuccess: (domain) => {
      invalidate();
      setFormOpen(false);
      setEditing(null);
      setFormError(null);
      setNotice({ tone: "success", text: `${domain.host}:${domain.port} diperbarui.` });
    },
    onError: (error) => {
      setFormError(errorMessage(error, "Gagal memperbarui target TLS."));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTlsDomain,
    onSuccess: () => {
      invalidate();
      setDeleteTarget(null);
      setNotice({ tone: "success", text: "Target TLS dihapus." });
    },
    onError: (error) => {
      setNotice({ tone: "error", text: errorMessage(error, "Gagal menghapus target TLS.") });
    },
  });

  const checkMutation = useMutation({
    mutationFn: checkTlsDomain,
    onSuccess: (domain) => {
      invalidate();
      if (domain.status === "healthy") {
        setNotice({
          tone: "success",
          text: `Sertifikat ${domain.host}:${domain.port} sehat.`,
        });
      } else {
        setNotice({
          tone: "error",
          text: `Pemeriksaan ${domain.host}:${domain.port} selesai: ${domain.status}. ${
            domain.error_message ?? ""
          }`.trim(),
        });
      }
    },
    onError: (error) => {
      setNotice({
        tone: "error",
        text: errorMessage(error, "Gagal memeriksa sertifikat."),
      });
    },
  });

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return domains.filter((domain) => {
      if (statusFilter !== "all" && domain.status !== statusFilter) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      return (
        domain.host.toLowerCase().includes(keyword) ||
        (domain.name ?? "").toLowerCase().includes(keyword) ||
        (domain.issuer ?? "").toLowerCase().includes(keyword)
      );
    });
  }, [domains, search, statusFilter]);

  const totals = useMemo(
    () =>
      domains.reduce(
        (accumulator, domain) => {
          if (domain.status === "healthy") {
            accumulator.healthy += 1;
          } else if (domain.status === "expiring") {
            accumulator.expiring += 1;
          } else if (["expired", "invalid", "error"].includes(domain.status)) {
            accumulator.problem += 1;
          } else {
            accumulator.pending += 1;
          }
          return accumulator;
        },
        { healthy: 0, expiring: 0, problem: 0, pending: 0 },
      ),
    [domains],
  );

  const listError = domainsQuery.error
    ? errorMessage(domainsQuery.error, "Tidak dapat memuat target TLS.")
    : null;
  const checkingId = checkMutation.isPending ? (checkMutation.variables ?? null) : null;
  const formPending = createMutation.isPending || updateMutation.isPending;

  function openCreate() {
    setEditing(null);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(domain: TlsDomainSummary) {
    setEditing(domain);
    setFormError(null);
    setFormOpen(true);
  }

  function handleSubmit(payload: TlsDomainCreatePayload | TlsDomainUpdatePayload) {
    if (editing) {
      const changes: TlsDomainUpdatePayload = {};
      if (payload.name !== editing.name) {
        changes.name = payload.name;
      }
      if (payload.host !== undefined && payload.host !== editing.host) {
        changes.host = payload.host;
      }
      if (payload.port !== undefined && payload.port !== editing.port) {
        changes.port = payload.port;
      }
      if (
        payload.warning_days !== undefined &&
        payload.warning_days !== editing.warning_days
      ) {
        changes.warning_days = payload.warning_days;
      }
      if (payload.enabled !== undefined && payload.enabled !== editing.enabled) {
        changes.enabled = payload.enabled;
      }
      if (Object.keys(changes).length === 0) {
        setFormOpen(false);
        return;
      }
      updateMutation.mutate({ id: editing.id, payload: changes });
      return;
    }
    createMutation.mutate(payload as TlsDomainCreatePayload);
  }

  return (
    <div className="space-y-6" data-testid="tls-domains-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <GlobeLock className="size-6 text-indigo-500" />
            TLS / SSL
          </h1>
          <p className="text-sm text-muted-foreground">
            Pantau masa berlaku dan validitas sertifikat domain reverse proxy.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          >
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
              <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500" />
            </span>
            Auto-refresh 60 detik
          </Badge>
          {canDeploy ? (
            <Button onClick={openCreate} data-testid="tls-domain-add">
              <Plus />
              Tambah target
            </Button>
          ) : null}
        </div>
      </div>

      {notice ? (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
            notice.tone === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
          )}
          data-testid="tls-domain-notice"
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

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Sehat"
          description={`${domains.length} target dipantau`}
          value={totals.healthy}
          icon={ShieldCheck}
          iconClassName="text-emerald-500"
          valueClassName="text-emerald-600 dark:text-emerald-400"
          loading={domainsQuery.isPending}
        />
        <SummaryCard
          title="Segera kedaluwarsa"
          description="Di dalam ambang warning"
          value={totals.expiring}
          icon={ShieldAlert}
          iconClassName="text-amber-500"
          valueClassName="text-amber-600 dark:text-amber-400"
          loading={domainsQuery.isPending}
        />
        <SummaryCard
          title="Bermasalah"
          description="Expired, invalid, atau error"
          value={totals.problem}
          icon={LockKeyhole}
          iconClassName="text-red-500"
          valueClassName="text-red-600 dark:text-red-400"
          loading={domainsQuery.isPending}
        />
        <SummaryCard
          title="Belum diperiksa"
          description="Termasuk target nonaktif"
          value={totals.pending}
          icon={Loader2}
          iconClassName="text-slate-500"
          valueClassName="text-slate-600 dark:text-slate-300"
          loading={domainsQuery.isPending}
        />
      </div>

      <Card size="sm">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Cari host, label, atau issuer"
              className="w-[280px] pl-8"
              aria-label="Cari target TLS"
              data-testid="tls-domain-search"
            />
          </div>
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as StatusFilter)}
          >
            <SelectTrigger className="w-[190px]" aria-label="Filter status TLS">
              <Filter className="size-3.5" />
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              {statusFilters.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground" data-testid="tls-domain-count">
            {filtered.length} dari {domains.length} target ditampilkan
            {total > domains.length ? ` · total ${total}` : ""}
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle className="text-base">Target TLS</CardTitle>
            <CardDescription>
              Pemeriksaan membuka koneksi TLS baru; hasil disimpan ke riwayat.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {domainsQuery.isPending ? (
            <div className="space-y-2">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-14 w-full rounded-lg" />
              ))}
            </div>
          ) : listError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <TriangleAlert className="size-6 text-destructive" />
              <p className="text-sm text-destructive">{listError}</p>
              <Button variant="outline" size="sm" onClick={() => void domainsQuery.refetch()}>
                Coba lagi
              </Button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <GlobeLock className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">
                {domains.length === 0 ? "Belum ada target TLS" : "Tidak ada target yang cocok"}
              </p>
              <p className="max-w-md text-xs text-muted-foreground">
                {domains.length === 0
                  ? canDeploy
                    ? "Tambahkan domain reverse proxy untuk mulai memantau sertifikat."
                    : "Hubungi Developer atau Admin untuk menambahkan target."
                  : "Ubah kata kunci atau filter status untuk melihat target lain."}
              </p>
            </div>
          ) : (
            <TlsDomainTable
              domains={filtered}
              checkingId={checkingId}
              canManage={canDeploy}
              onDetail={(domain) => setDetailId(domain.id)}
              onCheck={(domain) => checkMutation.mutate(domain.id)}
              onEdit={openEdit}
              onDelete={setDeleteTarget}
            />
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={() => void domainsQuery.refetch()}
          disabled={domainsQuery.isFetching}
        >
          <RefreshCw className={cn("size-3.5", domainsQuery.isFetching && "animate-spin")} />
          Muat ulang
        </Button>
      </div>

      <TlsDomainFormDialog
        key={`${formOpen ? "open" : "closed"}-${editing?.id ?? "new"}`}
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) {
            setEditing(null);
            setFormError(null);
          }
        }}
        domain={editing}
        isPending={formPending}
        error={formError}
        onSubmit={handleSubmit}
      />

      <TlsDomainDetailDialog
        domainId={detailId}
        open={detailId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDetailId(null);
          }
        }}
        canManage={canDeploy}
        isChecking={checkingId !== null}
        onCheck={(id) => checkMutation.mutate(id)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        title="Hapus target TLS?"
        description={
          deleteTarget
            ? `${deleteTarget.host}:${deleteTarget.port} beserta riwayat pemeriksaannya akan dihapus.`
            : undefined
        }
        confirmLabel="Hapus"
        variant="destructive"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id);
          }
        }}
      />
    </div>
  );
}
