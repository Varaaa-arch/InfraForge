import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { fetchLogContainers, fetchLogs } from "@/api/logs";
import { LogsToolbar } from "@/components/logs/logs-toolbar";
import { LogsViewer } from "@/components/logs/logs-viewer";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useLogStream } from "@/hooks/use-log-stream";
import { compareLogEntries, logEntryKey } from "@/lib/logs";
import type { LogEntry, LogLevel, LogRange } from "@/types/log";

export function LogsPage() {
  const [q, setQ] = useState("");
  const [container, setContainer] = useState("all");
  const [level, setLevel] = useState<LogLevel>("all");
  const [last, setLast] = useState<LogRange>("1h");
  const [live, setLive] = useState(false);

  const debouncedQ = useDebouncedValue(q, 400);
  const keyword = debouncedQ.trim() || undefined;
  const containerFilter = container === "all" ? undefined : container;

  const containersQuery = useQuery({
    queryKey: ["logs", "containers"],
    queryFn: fetchLogContainers,
    staleTime: 60_000,
  });

  const logsQuery = useQuery({
    queryKey: ["logs", containerFilter ?? "all", level, keyword ?? "", last],
    queryFn: () => fetchLogs({ container: containerFilter, level, q: keyword, last, limit: 500 }),
    placeholderData: keepPreviousData,
    refetchInterval: live ? false : 15_000,
  });

  const stream = useLogStream(live, {
    container: containerFilter,
    level,
    q: keyword,
  });

  const entries = useMemo<LogEntry[]>(() => {
    const merged = new Map<string, LogEntry>();

    for (const entry of logsQuery.data?.logs ?? []) {
      merged.set(logEntryKey(entry), entry);
    }
    for (const entry of stream.entries) {
      merged.set(logEntryKey(entry), entry);
    }

    return [...merged.values()].sort(compareLogEntries);
  }, [logsQuery.data?.logs, stream.entries]);

  const errorMessage = logsQuery.error
    ? logsQuery.error instanceof ApiError
      ? logsQuery.error.message
      : "Tidak dapat memuat log dari server."
    : null;

  return (
    <div className="flex h-[calc(100svh-5.5rem)] min-h-[560px] flex-col gap-4 sm:h-[calc(100svh-6.5rem)] lg:h-[calc(100svh-7.5rem)]">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Logs</h1>
        <p className="text-sm text-muted-foreground">
          Telusuri log terpusat dari Loki, filter per container/level, atau stream real-time.
        </p>
      </div>

      <LogsToolbar
        q={q}
        onQChange={setQ}
        container={container}
        onContainerChange={setContainer}
        containers={containersQuery.data?.containers ?? []}
        level={level}
        onLevelChange={setLevel}
        last={last}
        onLastChange={setLast}
        isFetching={logsQuery.isFetching}
        onRefresh={() => void logsQuery.refetch()}
      />

      <LogsViewer
        entries={entries}
        isLoading={logsQuery.isPending}
        isFetching={logsQuery.isFetching}
        errorMessage={errorMessage}
        onRetry={() => void logsQuery.refetch()}
        query={logsQuery.data?.query}
        live={live}
        onLiveChange={setLive}
        liveStatus={stream.status}
        liveError={stream.error}
      />
    </div>
  );
}
