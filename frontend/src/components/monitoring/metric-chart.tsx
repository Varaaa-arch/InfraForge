import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface ChartPoint {
  timestamp: number;
  [key: string]: number | undefined;
}

export interface ChartSeriesConfig {
  key: string;
  label: string;
  color: string;
}

export type ChartUnit = "percent" | "bytes_per_second";

interface MetricChartProps {
  title: string;
  description?: string;
  data: ChartPoint[];
  series: ChartSeriesConfig[];
  unit: ChartUnit;
  variant?: "area" | "line";
  loading?: boolean;
  className?: string;
}

const timeFormatter = new Intl.DateTimeFormat("id-ID", {
  hour: "2-digit",
  minute: "2-digit",
});

function formatTime(timestamp: number): string {
  return timeFormatter.format(new Date(timestamp));
}

function formatBytesPerSecond(value: number): string {
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB/s`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(1)} KB/s`;
  }
  return `${Math.round(value)} B/s`;
}

function formatValue(value: number, unit: ChartUnit): string {
  if (unit === "percent") {
    return `${value.toFixed(1)}%`;
  }
  return formatBytesPerSecond(value);
}

function formatAxisValue(value: number, unit: ChartUnit): string {
  if (unit === "percent") {
    return `${Math.round(value)}%`;
  }
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(0)}M`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(0)}K`;
  }
  return String(Math.round(value));
}

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: number | string;
  unit: ChartUnit;
}

function ChartTooltip({ active, payload, label, unit }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">
        {typeof label === "number" ? formatTime(label) : label}
      </p>
      <div className="space-y-0.5">
        {payload.map((item) => (
          <div key={item.name} className="flex items-center gap-1.5">
            <span
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-muted-foreground">{item.name}</span>
            <span className="ml-auto pl-3 font-medium tabular-nums text-popover-foreground">
              {formatValue(Number(item.value ?? 0), unit)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function latestValue(data: ChartPoint[], key: string): number | undefined {
  for (let index = data.length - 1; index >= 0; index -= 1) {
    const value = data[index][key];
    if (typeof value === "number") {
      return value;
    }
  }
  return undefined;
}

export function MetricChart({
  title,
  description,
  data,
  series,
  unit,
  variant = "area",
  loading = false,
  className,
}: MetricChartProps) {
  const gradientId = useId().replace(/[^a-zA-Z0-9]/g, "");

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="text-base">{title}</CardTitle>
            {description ? <CardDescription>{description}</CardDescription> : null}
          </div>
          {!loading && data.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              {series.map((item) => {
                const value = latestValue(data, item.key);
                if (value === undefined) {
                  return null;
                }
                return (
                  <span
                    key={item.key}
                    className="flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-xs"
                  >
                    <span
                      className="size-2 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="font-medium tabular-nums">
                      {formatValue(value, unit)}
                    </span>
                  </span>
                );
              })}
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-[220px] w-full rounded-lg" />
        ) : data.length === 0 ? (
          <div className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">
            Belum ada data untuk rentang ini.
          </div>
        ) : (
          <div className="h-[220px] w-full" data-testid="metric-chart">
            <ResponsiveContainer width="100%" height="100%">
              {variant === "area" ? (
                <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    {series.map((item) => (
                      <linearGradient
                        key={item.key}
                        id={`${gradientId}-${item.key}`}
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop offset="5%" stopColor={item.color} stopOpacity={0.35} />
                        <stop offset="95%" stopColor={item.color} stopOpacity={0.02} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.6} />
                  <XAxis
                    dataKey="timestamp"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={formatTime}
                    minTickGap={48}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    width={48}
                    tickFormatter={(value: number) => formatAxisValue(value, unit)}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip content={<ChartTooltip unit={unit} />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />
                  {series.map((item) => (
                    <Area
                      key={item.key}
                      type="monotone"
                      dataKey={item.key}
                      name={item.label}
                      stroke={item.color}
                      fill={`url(#${gradientId}-${item.key})`}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
                </AreaChart>
              ) : (
                <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.6} />
                  <XAxis
                    dataKey="timestamp"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={formatTime}
                    minTickGap={48}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    width={48}
                    tickFormatter={(value: number) => formatAxisValue(value, unit)}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip content={<ChartTooltip unit={unit} />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />
                  {series.map((item) => (
                    <Line
                      key={item.key}
                      type="monotone"
                      dataKey={item.key}
                      name={item.label}
                      stroke={item.color}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
