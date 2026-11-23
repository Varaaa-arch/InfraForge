import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Boxes,
  Bug,
  CircleCheck,
  GlobeLock,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { fetchSecurityPosture } from "@/api/security-posture";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type {
  PostureCheck,
  PostureFinding,
  PostureLevel,
  PostureSeverity,
} from "@/types/security-posture";

const LEVEL_META: Record<
  string,
  {
    label: string;
    icon: typeof ShieldCheck;
    badgeClass: string;
    scoreClass: string;
    barClass: string;
    helper: string;
  }
> = {
  aman: {
    label: "Aman",
    icon: ShieldCheck,
    badgeClass:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    scoreClass: "text-emerald-600 dark:text-emerald-400",
    barClass: "bg-emerald-500",
    helper: "Posture sesuai baseline keamanan yang dipantau.",
  },
  perlu_perhatian: {
    label: "Perlu perhatian",
    icon: TriangleAlert,
    badgeClass:
      "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
    scoreClass: "text-amber-600 dark:text-amber-400",
    barClass: "bg-amber-500",
    helper: "Ada temuan yang sebaiknya ditinjau sebelum menjadi insiden.",
  },
  berisiko: {
    label: "Berisiko",
    icon: ShieldAlert,
    badgeClass: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
    scoreClass: "text-red-600 dark:text-red-400",
    barClass: "bg-red-500",
    helper: "Prioritaskan remediasi temuan critical/expired di bawah.",
  },
};

const CHECK_META: Record<
  string,
  { icon: typeof CircleCheck; className: string; label: string }
> = {
  pass: {
    icon: CircleCheck,
    className: "text-emerald-600 dark:text-emerald-400",
    label: "Lulus",
  },
  warn: {
    icon: TriangleAlert,
    className: "text-amber-600 dark:text-amber-400",
    label: "Perhatian",
  },
  fail: {
    icon: ShieldAlert,
    className: "text-red-600 dark:text-red-400",
    label: "Gagal",
  },
  unknown: {
    icon: Loader2,
    className: "text-slate-500",
    label: "Unknown",
  },
};

const SEVERITY_CLASS: Record<PostureSeverity, string> = {
  critical:
    "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  high: "border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400",
  warning:
    "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400",
};

function levelMeta(level: PostureLevel) {
  return (
    LEVEL_META[level] ?? {
      label: level,
      icon: ShieldAlert,
      badgeClass: "border-border text-muted-foreground",
      scoreClass: "text-foreground",
      barClass: "bg-slate-500",
      helper: "Posture belum dapat diklasifikasikan.",
    }
  );
}

function FindingRow({ finding }: { finding: PostureFinding }) {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border px-3 py-2"
      data-testid="security-posture-finding"
    >
      <span
        className={cn(
          "mt-0.5 inline-flex shrink-0 rounded-full border px-2 py-0.5 text-[0.65rem] font-medium uppercase",
          SEVERITY_CLASS[finding.severity] ?? SEVERITY_CLASS.info,
        )}
      >
        {finding.severity}
      </span>
      <div className="min-w-0 space-y-0.5">
        <p className="truncate text-sm font-medium">{finding.title}</p>
        <p className="text-xs text-muted-foreground">{finding.detail}</p>
        {finding.resource ? (
          <p className="truncate font-mono text-[0.7rem] text-muted-foreground">
            {finding.resource}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function CheckRow({ check }: { check: PostureCheck }) {
  const meta = CHECK_META[check.status] ?? CHECK_META.unknown;
  const Icon = meta.icon;
  return (
    <div className="flex items-start gap-2 py-1.5" data-testid="security-posture-check">
      <Icon className={cn("mt-0.5 size-4 shrink-0", meta.className)} />
      <div className="min-w-0">
        <p className="text-sm font-medium">
          {check.title}
          {check.count > 0 ? (
            <span className="ml-1.5 text-xs text-muted-foreground">({check.count})</span>
          ) : null}
        </p>
        <p className="text-xs text-muted-foreground">{check.detail}</p>
      </div>
      <span className="ml-auto shrink-0 text-[0.65rem] text-muted-foreground uppercase">
        {meta.label}
      </span>
    </div>
  );
}

export function SecurityPostureCard({ className }: { className?: string }) {
  const postureQuery = useQuery({
    queryKey: ["security-posture"],
    queryFn: fetchSecurityPosture,
    refetchInterval: 30_000,
    retry: 1,
  });

  const posture = postureQuery.data;
  const meta = levelMeta(posture?.level ?? "perlu_perhatian");
  const LevelIcon = meta.icon;
  const attentionChecks = (posture?.checks ?? [])
    .filter((check) => check.status !== "pass")
    .slice(0, 6);
  const findings = (posture?.findings ?? []).slice(0, 5);
  const error =
    postureQuery.error instanceof ApiError
      ? postureQuery.error.message
      : "Tidak dapat memuat posture keamanan.";

  return (
    <Card className={cn("overflow-hidden", className)} data-testid="security-posture-card">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="size-4 text-indigo-500" />
            Posture Keamanan
          </CardTitle>
          <CardDescription>
            Agregasi CVE image, status TLS, dan konfigurasi container yang sedang berjalan.
          </CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void postureQuery.refetch()}
          disabled={postureQuery.isFetching}
          data-testid="security-posture-refresh"
        >
          <RefreshCw className={cn("size-3.5", postureQuery.isFetching && "animate-spin")} />
          Muat ulang
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {postureQuery.isPending ? (
          <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
            <Skeleton className="h-40 w-full rounded-xl" />
            <Skeleton className="h-40 w-full rounded-xl" />
          </div>
        ) : postureQuery.isError || !posture ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void postureQuery.refetch()}>
              Coba lagi
            </Button>
          </div>
        ) : (
          <>
            <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="rounded-xl border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Skor
                  </span>
                  <Badge
                    variant="outline"
                    className={cn("gap-1.5", meta.badgeClass)}
                    data-testid="security-posture-level"
                  >
                    <LevelIcon className="size-3" />
                    {meta.label}
                  </Badge>
                </div>
                <div className="mt-3 flex items-baseline gap-1">
                  <span
                    className={cn("text-4xl font-semibold tabular-nums", meta.scoreClass)}
                    data-testid="security-posture-score"
                  >
                    {posture.score}
                  </span>
                  <span className="text-sm text-muted-foreground">/100</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full transition-all", meta.barClass)}
                    style={{ width: `${posture.score}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{meta.helper}</p>
                <p className="mt-1 text-[0.7rem] text-muted-foreground">
                  Diperbarui{" "}
                  {new Intl.DateTimeFormat("id-ID", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(posture.generated_at))}
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border p-3" data-testid="security-posture-image">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Bug className="size-3.5" />
                    Image CVE
                  </div>
                  <p className="mt-1 text-2xl font-semibold tabular-nums">
                    {posture.images.critical_count + posture.images.high_count}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {posture.images.critical_count} critical · {posture.images.high_count} high
                  </p>
                  <p className="mt-1 text-[0.7rem] text-muted-foreground">
                    {posture.images.total_scans} scan · {posture.images.failed} gagal
                  </p>
                </div>
                <div className="rounded-lg border p-3" data-testid="security-posture-tls">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <GlobeLock className="size-3.5" />
                    TLS / SSL
                  </div>
                  <p className="mt-1 text-2xl font-semibold tabular-nums">
                    {posture.tls.expired + posture.tls.invalid + posture.tls.error}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {posture.tls.expired} expired · {posture.tls.invalid} invalid
                  </p>
                  <p className="mt-1 text-[0.7rem] text-muted-foreground">
                    {posture.tls.healthy} sehat · {posture.tls.expiring} segera
                  </p>
                </div>
                <div className="rounded-lg border p-3" data-testid="security-posture-container">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Boxes className="size-3.5" />
                    Container
                  </div>
                  {posture.containers.available ? (
                    <>
                      <p className="mt-1 text-2xl font-semibold tabular-nums">
                        {posture.containers.privileged + posture.containers.root_user}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {posture.containers.privileged} privileged ·{" "}
                        {posture.containers.root_user} root
                      </p>
                      <p className="mt-1 text-[0.7rem] text-muted-foreground">
                        {posture.containers.running} berjalan dari {posture.containers.total}
                      </p>
                    </>
                  ) : (
                    <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                      {posture.containers.error_message ?? "Docker tidak tersedia."}
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-medium">Temuan teratas</h3>
                  <Badge variant="outline" className="text-[0.65rem]">
                    {posture.findings.length} temuan
                  </Badge>
                </div>
                {findings.length === 0 ? (
                  <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-4 text-sm text-emerald-700 dark:text-emerald-400">
                    <CircleCheck className="size-4" />
                    Tidak ada temuan critical/high yang perlu ditindaklanjuti.
                  </div>
                ) : (
                  <div className="space-y-2" data-testid="security-posture-findings">
                    {findings.map((finding, index) => (
                      <FindingRow
                        key={`${finding.category}-${finding.resource ?? "global"}-${index}`}
                        finding={finding}
                      />
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <h3 className="text-sm font-medium">Pemeriksaan yang perlu perhatian</h3>
                {attentionChecks.length === 0 ? (
                  <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-4 text-sm text-emerald-700 dark:text-emerald-400">
                    <ShieldCheck className="size-4" />
                    Semua pemeriksaan posture lulus.
                  </div>
                ) : (
                  <div className="divide-y rounded-lg border px-3" data-testid="security-posture-checks">
                    {attentionChecks.map((check) => (
                      <CheckRow key={check.key} check={check} />
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-2">
              <Button asChild variant="outline" size="sm">
                <Link to="/security">
                  Buka keamanan
                  <ArrowRight className="size-3.5" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link to="/tls-domains">
                  Buka TLS / SSL
                  <ArrowRight className="size-3.5" />
                </Link>
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
