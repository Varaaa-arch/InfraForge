import {
  Check,
  Copy,
  Loader2,
  RefreshCw,
  ScrollText,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
import {
  useDeploymentLogStream,
  type DeploymentLogStreamStatus,
} from "@/hooks/use-deployment-log-stream";
import { cn } from "@/lib/utils";
import type { Deployment } from "@/types/deployment";

const statusMeta: Record<
  DeploymentLogStreamStatus,
  { label: string; className: string }
> = {
  connecting: {
    label: "Menghubungkan",
    className:
      "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  streaming: {
    label: "Live",
    className:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  done: {
    label: "Selesai",
    className:
      "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
  error: {
    label: "Error",
    className: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
  },
};

interface DeploymentLogDialogProps {
  deployment: Deployment | null;
  applicationName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeploymentLogDialog({
  deployment,
  applicationName,
  open,
  onOpenChange,
}: DeploymentLogDialogProps) {
  const { lines, status, error, retry } = useDeploymentLogStream(
    deployment?.id ?? null,
    open,
  );
  const outputRef = useRef<HTMLDivElement>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );
  const meta = statusMeta[status];

  useEffect(() => {
    const output = outputRef.current;
    if (output) {
      output.scrollTop = output.scrollHeight;
    }
  }, [lines, status]);

  async function copyLogs() {
    const text = lines.join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
      return;
    } catch {
      // Fallback untuk browser/konteks tanpa Clipboard API.
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    setCopyState(copied ? "copied" : "error");
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-4xl"
        data-testid="deployment-log-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScrollText className="size-4" />
            Log deployment #{deployment?.id ?? "—"}
          </DialogTitle>
          <DialogDescription>
            {applicationName}
            {deployment ? ` · branch ${deployment.branch}` : ""} — baris baru
            ditampilkan langsung saat proses build dan compose berjalan.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn("gap-1.5", meta.className)}
                data-testid="deployment-log-status"
              >
                {status === "connecting" ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : status === "streaming" ? (
                  <span className="size-1.5 animate-pulse rounded-full bg-current" />
                ) : null}
                {meta.label}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {lines.length} baris
              </span>
            </div>
            {error ? (
              <p
                className="flex items-center gap-1.5 text-xs text-destructive"
                data-testid="deployment-log-error"
              >
                <TriangleAlert className="size-3.5 shrink-0" />
                {error}
              </p>
            ) : null}
          </div>

          <div
            ref={outputRef}
            className="h-[420px] overflow-auto rounded-lg border bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-200"
            data-testid="deployment-log-output"
          >
            {lines.length === 0 ? (
              <p className="text-zinc-500">
                {status === "error"
                  ? "Tidak ada log yang dapat ditampilkan."
                  : "Menunggu log dari server…"}
              </p>
            ) : (
              lines.map((line, index) => (
                <div
                  key={index}
                  className="whitespace-pre-wrap break-words"
                  data-testid="deployment-log-line"
                >
                  {line || "\u00a0"}
                </div>
              ))
            )}
          </div>

          {copyState === "error" ? (
            <p className="text-xs text-destructive">
              Gagal menyalin log — pilih teks di atas secara manual.
            </p>
          ) : null}
        </div>

        <DialogFooter>
          {status === "error" ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setCopyState("idle");
                retry();
              }}
              data-testid="deployment-log-retry"
            >
              <RefreshCw className="size-3.5" />
              Sambungkan ulang
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            onClick={() => void copyLogs()}
            disabled={lines.length === 0}
            data-testid="deployment-log-copy"
          >
            {copyState === "copied" ? (
              <Check className="size-3.5" />
            ) : (
              <Copy className="size-3.5" />
            )}
            {copyState === "copied" ? "Tersalin" : "Salin log"}
          </Button>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Tutup
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
