import { useEffect, useRef, useState } from "react";

import { ensureValidAccessToken, WS_BASE_URL } from "@/api/client";
import { logEntryKey } from "@/lib/logs";
import type { LogEntry, LogLevel } from "@/types/log";

const MAX_LIVE_ENTRIES = 1000;
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 15000;

export type LogStreamStatus = "idle" | "connecting" | "open" | "closed" | "error";

export interface LogStreamFilters {
  container?: string;
  level: LogLevel;
  q?: string;
}

export interface LogStreamState {
  entries: LogEntry[];
  status: LogStreamStatus;
  error: string | null;
}

function isLogEntry(value: unknown): value is LogEntry {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.timestamp === "string" &&
    typeof record.timestamp_ns === "string" &&
    typeof record.line === "string"
  );
}

function buildStreamUrl(token: string, filters: LogStreamFilters): string {
  const params = new URLSearchParams({ token });

  if (filters.container && filters.container !== "all") {
    params.set("container", filters.container);
  }
  if (filters.level !== "all") {
    params.set("level", filters.level);
  }
  if (filters.q) {
    params.set("q", filters.q);
  }

  return `${WS_BASE_URL}/ws/logs?${params.toString()}`;
}

export function useLogStream(
  enabled: boolean,
  filters: LogStreamFilters,
): LogStreamState {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [status, setStatus] = useState<LogStreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const seenRef = useRef(new Set<string>());
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const attemptRef = useRef(0);

  const { container, level, q } = filters;

  useEffect(() => {
    let cancelled = false;
    let fatal = false;

    seenRef.current.clear();
    setEntries([]);
    setError(null);

    if (!enabled) {
      setStatus("idle");
      return;
    }

    const scheduleReconnect = () => {
      if (cancelled || fatal) {
        return;
      }
      const delay = Math.min(
        RECONNECT_BASE_DELAY * 2 ** attemptRef.current,
        RECONNECT_MAX_DELAY,
      );
      attemptRef.current += 1;
      reconnectTimerRef.current = window.setTimeout(() => {
        void connect();
      }, delay);
    };

    const connect = async () => {
      setStatus("connecting");
      setError(null);

      const token = await ensureValidAccessToken();
      if (cancelled) {
        return;
      }
      if (!token) {
        setStatus("error");
        setError("Sesi login tidak valid. Silakan login ulang.");
        return;
      }

      const socket = new WebSocket(buildStreamUrl(token, { container, level, q }));
      socketRef.current = socket;

      socket.onopen = () => {
        attemptRef.current = 0;
        setStatus("open");
        setError(null);
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        let payload: unknown;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }

        if (
          typeof payload === "object" &&
          payload !== null &&
          "error" in payload &&
          typeof (payload as { error?: unknown }).error === "string"
        ) {
          fatal = true;
          setStatus("error");
          setError((payload as { error: string }).error);
          return;
        }

        if (!isLogEntry(payload)) {
          return;
        }

        const key = logEntryKey(payload);
        if (seenRef.current.has(key)) {
          return;
        }
        seenRef.current.add(key);

        setEntries((previous) => {
          const next = [...previous, payload];
          if (next.length > MAX_LIVE_ENTRIES) {
            const removed = next.splice(0, next.length - MAX_LIVE_ENTRIES);
            for (const entry of removed) {
              seenRef.current.delete(logEntryKey(entry));
            }
          }
          return next;
        });
      };

      socket.onerror = () => {
        setError("Koneksi live tail terputus.");
      };

      socket.onclose = (event) => {
        socketRef.current = null;
        if (cancelled) {
          return;
        }
        if (fatal || event.code === 4001 || event.code === 4002) {
          setStatus("error");
          return;
        }
        setStatus("closed");
        scheduleReconnect();
      };
    };

    void connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [enabled, container, level, q]);

  return { entries, status, error };
}
