import type { LogEntry } from "@/types/log";

const ESCAPE_CHAR = String.fromCharCode(27);
const ANSI_PATTERN = new RegExp(
  `${ESCAPE_CHAR}\\[[0-?]*[ -/]*[@-~]`,
  "g",
);

export function stripAnsi(line: string): string {
  return line.replace(ANSI_PATTERN, "");
}

export function formatLogTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--.---";
  }

  const pad = (value: number, length = 2) => String(value).padStart(length, "0");
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}`;
  const isToday = date.toDateString() === new Date().toDateString();

  if (isToday) {
    return time;
  }
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)} ${time}`;
}

export interface LevelStyle {
  label: string;
  className: string;
}

export function getLevelStyle(level: string | null): LevelStyle {
  switch ((level ?? "").toLowerCase()) {
    case "error":
    case "err":
    case "critical":
    case "fatal":
      return {
        label: "error",
        className: "border-red-500/25 bg-red-500/10 text-red-400",
      };
    case "warn":
    case "warning":
      return {
        label: "warn",
        className: "border-amber-500/25 bg-amber-500/10 text-amber-400",
      };
    case "info":
      return {
        label: "info",
        className: "border-sky-500/25 bg-sky-500/10 text-sky-400",
      };
    case "debug":
    case "trace":
      return {
        label: level?.toLowerCase() ?? "debug",
        className: "border-zinc-500/25 bg-zinc-500/10 text-zinc-400",
      };
    default:
      return {
        label: "log",
        className: "border-border bg-muted/60 text-muted-foreground",
      };
  }
}

export function logEntryKey(entry: LogEntry): string {
  return `${entry.timestamp_ns}|${entry.container ?? ""}|${entry.stream ?? ""}|${entry.line}`;
}

export function compareLogEntries(a: LogEntry, b: LogEntry): number {
  try {
    const left = BigInt(a.timestamp_ns);
    const right = BigInt(b.timestamp_ns);
    if (left < right) return -1;
    if (left > right) return 1;
    return 0;
  } catch {
    return a.timestamp_ns.localeCompare(b.timestamp_ns);
  }
}
