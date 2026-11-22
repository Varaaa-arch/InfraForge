import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { VulnerabilitySeverity } from "@/types/image-scan";

const severityStyles: Record<string, { label: string; className: string }> = {
  critical: {
    label: "Critical",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  high: {
    label: "High",
    className: "border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400",
  },
  medium: {
    label: "Medium",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  low: {
    label: "Low",
    className: "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  },
  none: {
    label: "Bersih",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  unknown: {
    label: "Unknown",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
};

export function SeverityBadge({
  severity,
  className,
}: {
  severity: VulnerabilitySeverity | null;
  className?: string;
}) {
  const style = severityStyles[severity ?? "unknown"] ?? {
    label: String(severity || "Unknown"),
    className:
      "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  };

  return (
    <Badge variant="outline" className={cn("gap-1.5", style.className, className)}>
      <span className="size-1.5 rounded-full bg-current" />
      {style.label}
    </Badge>
  );
}
