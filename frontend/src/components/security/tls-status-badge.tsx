import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TlsDomainStatus } from "@/types/tls-domain";

const statusStyles: Record<string, { label: string; className: string }> = {
  pending: {
    label: "Belum diperiksa",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
  healthy: {
    label: "Sehat",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  expiring: {
    label: "Segera kedaluwarsa",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  expired: {
    label: "Kedaluwarsa",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  invalid: {
    label: "Tidak valid",
    className: "border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400",
  },
  error: {
    label: "Error",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

export function TlsStatusBadge({
  status,
  className,
}: {
  status: TlsDomainStatus;
  className?: string;
}) {
  const style = statusStyles[status] ?? {
    label: status,
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  };

  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 whitespace-nowrap", style.className, className)}
      data-testid="tls-status-badge"
    >
      <span className="size-1.5 rounded-full bg-current" />
      {style.label}
    </Badge>
  );
}
