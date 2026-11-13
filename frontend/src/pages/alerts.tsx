import { useQuery } from "@tanstack/react-query";
import { BellRing, CheckCircle2, Webhook } from "lucide-react";
import { useState } from "react";

import { fetchAlertChannels, fetchAlerts } from "@/api/alerts";
import { AlertChannels } from "@/components/alerts/alert-channels";
import { AlertHistory } from "@/components/alerts/alert-history";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Tab = "history" | "channels";

function SummaryCard({
  title,
  description,
  value,
  icon: Icon,
  iconClassName,
  loading,
}: {
  title: string;
  description: string;
  value: string | number;
  icon: typeof BellRing;
  iconClassName: string;
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
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        )}
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

export function AlertsPage() {
  const [tab, setTab] = useState<Tab>("history");

  const summaryQuery = useQuery({
    queryKey: ["alerts", "summary"],
    queryFn: () => fetchAlerts({ limit: 200 }),
    refetchInterval: 15_000,
  });

  const channelsQuery = useQuery({
    queryKey: ["alert-channels"],
    queryFn: fetchAlertChannels,
  });

  const alerts = summaryQuery.data ?? [];
  const firingCount = alerts.filter((alert) => alert.status === "firing").length;
  const resolvedCount = alerts.filter((alert) => alert.status === "resolved").length;
  const channels = channelsQuery.data ?? [];
  const enabledChannels = channels.filter((channel) => channel.enabled).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Alerts</h1>
          <p className="text-sm text-muted-foreground">
            Pantau alert dari Prometheus dan atur tujuan notifikasi Discord/Telegram.
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
          Auto-refresh 15 detik
        </Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          title="Firing"
          description="Sedang berlangsung"
          value={firingCount}
          icon={BellRing}
          iconClassName="text-red-500"
          loading={summaryQuery.isPending}
        />
        <SummaryCard
          title="Resolved"
          description="Dari 200 alert terbaru"
          value={resolvedCount}
          icon={CheckCircle2}
          iconClassName="text-emerald-500"
          loading={summaryQuery.isPending}
        />
        <SummaryCard
          title="Channel aktif"
          description={`${enabledChannels} dari ${channels.length} channel`}
          value={enabledChannels}
          icon={Webhook}
          iconClassName="text-indigo-500"
          loading={channelsQuery.isPending}
        />
      </div>

      <div
        className="inline-flex items-center gap-1 rounded-lg border bg-muted/40 p-1"
        role="tablist"
        aria-label="Bagian alert"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tab === "history"}
          onClick={() => setTab("history")}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm transition-colors",
            tab === "history"
              ? "bg-background font-medium text-foreground shadow-sm ring-1 ring-foreground/10"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          Riwayat alert
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "channels"}
          onClick={() => setTab("channels")}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm transition-colors",
            tab === "channels"
              ? "bg-background font-medium text-foreground shadow-sm ring-1 ring-foreground/10"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          Channel notifikasi
        </button>
      </div>

      {tab === "history" ? <AlertHistory /> : <AlertChannels />}
    </div>
  );
}
