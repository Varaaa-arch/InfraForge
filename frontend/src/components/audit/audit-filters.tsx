import { RefreshCw, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { AuditFilterMeta } from "@/types/audit-log";

interface AuditFiltersProps {
  meta: AuditFilterMeta | undefined;
  username: string;
  action: string;
  dateFrom: string;
  dateTo: string;
  isFetching: boolean;
  total: number;
  onUsernameChange: (value: string) => void;
  onActionChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onReset: () => void;
  onRefresh: () => void;
}

export function AuditFilters({
  meta,
  username,
  action,
  dateFrom,
  dateTo,
  isFetching,
  total,
  onUsernameChange,
  onActionChange,
  onDateFromChange,
  onDateToChange,
  onReset,
  onRefresh,
}: AuditFiltersProps) {
  const isAdmin = meta?.is_admin ?? false;

  return (
    <Card size="sm">
      <CardContent className="flex flex-wrap items-end gap-3 p-3">
        <div className="space-y-1.5">
          <Label htmlFor="audit-user" className="text-xs text-muted-foreground">
            User
          </Label>
          {isAdmin ? (
            <Select value={username} onValueChange={onUsernameChange}>
              <SelectTrigger
                id="audit-user"
                className="w-[190px]"
                aria-label="Filter user audit"
                data-testid="audit-filter-user"
              >
                <SelectValue placeholder="Semua user" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua user</SelectItem>
                {(meta?.usernames ?? []).map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div
              className="flex h-9 w-[190px] items-center rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground"
              data-testid="audit-scope-self"
            >
              Aktivitas saya
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="audit-action" className="text-xs text-muted-foreground">
            Jenis aksi
          </Label>
          <Select value={action} onValueChange={onActionChange}>
            <SelectTrigger
              id="audit-action"
              className="w-[190px]"
              aria-label="Filter jenis aksi"
              data-testid="audit-filter-action"
            >
              <SelectValue placeholder="Semua aksi" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua aksi</SelectItem>
              {(meta?.actions ?? []).map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="audit-from" className="text-xs text-muted-foreground">
            Dari
          </Label>
          <Input
            id="audit-from"
            type="datetime-local"
            className="w-[200px]"
            value={dateFrom}
            onChange={(event) => onDateFromChange(event.target.value)}
            data-testid="audit-filter-from"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="audit-to" className="text-xs text-muted-foreground">
            Sampai
          </Label>
          <Input
            id="audit-to"
            type="datetime-local"
            className="w-[200px]"
            value={dateTo}
            onChange={(event) => onDateToChange(event.target.value)}
            data-testid="audit-filter-to"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onReset}
            data-testid="audit-reset"
          >
            <RotateCcw className="size-3.5" />
            Reset
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isFetching}
            data-testid="audit-refresh"
          >
            <RefreshCw className={cn("size-3.5", isFetching && "animate-spin")} />
            Muat ulang
          </Button>
        </div>

        <span
          className="ml-auto text-xs text-muted-foreground"
          data-testid="audit-total"
        >
          {total} aktivitas
        </span>
      </CardContent>
    </Card>
  );
}
