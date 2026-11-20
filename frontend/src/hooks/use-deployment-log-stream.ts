import { useEffect, useState } from "react";

import { ensureValidAccessToken, WS_BASE_URL } from "@/api/client";

const MAX_LINES = 5000;
const DONE_SENTINEL = "[INFRAFORGE:DONE]";
const ERROR_PREFIX = "[INFRAFORGE:ERROR]";

export type DeploymentLogStreamStatus =
  | "connecting"
  | "streaming"
  | "done"
  | "error";

export interface DeploymentLogStreamState {
  lines: string[];
  status: DeploymentLogStreamStatus;
  error: string | null;
  retry: () => void;
}

export function useDeploymentLogStream(
  deploymentId: number | null,
  enabled: boolean,
): DeploymentLogStreamState {
  const [lines, setLines] = useState<string[]>([]);
  const [status, setStatus] =
    useState<DeploymentLogStreamStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled || deploymentId === null) {
      return;
    }

    let cancelled = false;
    let finished = false;
    let failed = false;
    let frame: number | null = null;
    let socket: WebSocket | null = null;
    const buffer: string[] = [];

    const flush = () => {
      frame = null;
      if (buffer.length === 0) {
        return;
      }
      const incoming = buffer.splice(0, buffer.length);
      setLines((previous) => {
        const next = previous.concat(incoming);
        return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
      });
    };

    const append = (line: string) => {
      buffer.push(line);
      if (frame === null) {
        frame = window.requestAnimationFrame(flush);
      }
    };

    const connect = async () => {
      setStatus("connecting");
      setError(null);
      setLines([]);

      const token = await ensureValidAccessToken();
      if (cancelled) {
        return;
      }
      if (!token) {
        setStatus("error");
        setError("Sesi login tidak valid. Silakan login ulang.");
        return;
      }

      const params = new URLSearchParams({ token });
      socket = new WebSocket(
        `${WS_BASE_URL}/ws/deployments/${deploymentId}/logs?${params.toString()}`,
      );

      socket.onopen = () => {
        if (!cancelled) {
          setStatus("streaming");
          setError(null);
        }
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        if (cancelled) {
          return;
        }
        const message = typeof event.data === "string" ? event.data : "";
        if (message === DONE_SENTINEL) {
          finished = true;
          flush();
          setStatus("done");
          socket?.close();
          return;
        }
        if (message.startsWith(ERROR_PREFIX)) {
          failed = true;
          const detail = message.slice(ERROR_PREFIX.length).trim();
          setError(detail || "Streaming log gagal.");
          setStatus("error");
          return;
        }
        append(message);
      };

      socket.onclose = () => {
        if (cancelled || finished || failed) {
          return;
        }
        flush();
        setStatus("error");
        setError("Koneksi log terputus. Coba sambungkan ulang.");
      };
    };

    void connect();

    return () => {
      cancelled = true;
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
      }
      socket?.close();
      socket = null;
    };
  }, [deploymentId, enabled, attempt]);

  return {
    lines,
    status,
    error,
    retry: () => setAttempt((current) => current + 1),
  };
}
