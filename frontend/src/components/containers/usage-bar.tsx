interface UsageBarProps {
  label: string;
  value: string;
  percent: number;
  color: string;
  testId?: string;
}

export function UsageBar({ label, value, percent, color, testId }: UsageBarProps) {
  const width = Math.min(100, Math.max(0, percent));

  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex items-baseline justify-between gap-2 text-[11px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${width}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}
