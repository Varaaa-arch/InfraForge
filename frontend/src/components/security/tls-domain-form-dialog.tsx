import { Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type {
  TlsDomainCreatePayload,
  TlsDomainSummary,
  TlsDomainUpdatePayload,
} from "@/types/tls-domain";

interface TlsDomainFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  domain: TlsDomainSummary | null;
  isPending: boolean;
  error: string | null;
  onSubmit: (payload: TlsDomainCreatePayload | TlsDomainUpdatePayload) => void;
}

export function TlsDomainFormDialog({
  open,
  onOpenChange,
  domain,
  isPending,
  error,
  onSubmit,
}: TlsDomainFormDialogProps) {
  const editing = domain !== null;
  const [name, setName] = useState(domain?.name ?? "");
  const [host, setHost] = useState(domain?.host ?? "");
  const [port, setPort] = useState(String(domain?.port ?? 443));
  const [warningDays, setWarningDays] = useState(String(domain?.warning_days ?? 30));
  const [enabled, setEnabled] = useState(domain?.enabled ?? true);
  const [checkNow, setCheckNow] = useState(true);

  const portNumber = Number(port);
  const warningNumber = Number(warningDays);
  const valid =
    host.trim().length > 0 &&
    Number.isInteger(portNumber) &&
    portNumber >= 1 &&
    portNumber <= 65535 &&
    Number.isInteger(warningNumber) &&
    warningNumber >= 1 &&
    warningNumber <= 365;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || isPending) {
      return;
    }
    const common = {
      name: name.trim() || null,
      host: host.trim(),
      port: portNumber,
      warning_days: warningNumber,
    };
    if (editing) {
      onSubmit({ ...common, enabled });
    } else {
      onSubmit({ ...common, enabled, check_now: checkNow });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="tls-domain-form-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-muted-foreground" />
            {editing ? "Ubah target TLS" : "Tambah target TLS"}
          </DialogTitle>
          <DialogDescription>
            Masukkan hostname atau IP tanpa skema dan path. Port default 443.
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="tls-name">Label (opsional)</Label>
            <Input
              id="tls-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Website utama"
              maxLength={100}
              disabled={isPending}
              data-testid="tls-domain-name"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_110px]">
            <div className="space-y-1.5">
              <Label htmlFor="tls-host">Hostname / IP</Label>
              <Input
                id="tls-host"
                value={host}
                onChange={(event) => setHost(event.target.value)}
                placeholder="example.com"
                autoComplete="off"
                spellCheck={false}
                className="font-mono text-xs"
                disabled={isPending}
                data-testid="tls-domain-host"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tls-port">Port</Label>
              <Input
                id="tls-port"
                type="number"
                min={1}
                max={65535}
                value={port}
                onChange={(event) => setPort(event.target.value)}
                className="font-mono text-xs"
                disabled={isPending}
                data-testid="tls-domain-port"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="tls-warning-days">Peringatkan sebelum (hari)</Label>
            <Input
              id="tls-warning-days"
              type="number"
              min={1}
              max={365}
              value={warningDays}
              onChange={(event) => setWarningDays(event.target.value)}
              disabled={isPending}
              data-testid="tls-domain-warning-days"
            />
            <p className="text-xs text-muted-foreground">
              Status menjadi “Segera kedaluwarsa” bila sisa masa berlaku ≤ nilai ini.
            </p>
          </div>

          <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
            <div className="space-y-0.5">
              <Label htmlFor="tls-enabled">Aktif dipantau</Label>
              <p className="text-xs text-muted-foreground">
                Target nonaktif tetap tersimpan tetapi tidak memicu alert.
              </p>
            </div>
            <Switch
              id="tls-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
              disabled={isPending}
            />
          </div>

          {editing ? null : (
            <div className="flex items-center justify-between rounded-lg border px-3 py-2.5">
              <div className="space-y-0.5">
                <Label htmlFor="tls-check-now">Periksa sekarang</Label>
                <p className="text-xs text-muted-foreground">
                  Buka koneksi TLS dan simpan hasil pemeriksaan pertama.
                </p>
              </div>
              <Switch
                id="tls-check-now"
                checked={checkNow}
                onCheckedChange={setCheckNow}
                disabled={isPending}
              />
            </div>
          )}

          {error ? (
            <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              Batal
            </Button>
            <Button type="submit" disabled={!valid || isPending} data-testid="tls-domain-submit">
              {isPending ? <Loader2 className="animate-spin" /> : null}
              {editing ? "Simpan perubahan" : "Tambah target"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
