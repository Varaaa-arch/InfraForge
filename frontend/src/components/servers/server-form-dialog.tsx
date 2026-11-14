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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Server, ServerAuthType } from "@/types/server";

interface FormState {
  name: string;
  host: string;
  port: string;
  username: string;
  auth_type: ServerAuthType;
  password: string;
  private_key: string;
  exporter_instance: string;
}

interface ServerFormValues {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: ServerAuthType;
  password?: string;
  private_key?: string;
  exporter_instance?: string;
}

interface ServerFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  server: Server | null;
  isPending?: boolean;
  errorMessage?: string | null;
  onSubmit: (values: ServerFormValues) => void;
}

function emptyForm(): FormState {
  return {
    name: "",
    host: "",
    port: "22",
    username: "",
    auth_type: "password",
    password: "",
    private_key: "",
    exporter_instance: "",
  };
}

function formFromServer(server: Server): FormState {
  return {
    name: server.name,
    host: server.host,
    port: String(server.port),
    username: server.username,
    auth_type: server.auth_type,
    password: "",
    private_key: "",
    exporter_instance: server.exporter_instance ?? "",
  };
}

export function ServerFormDialog({
  open,
  onOpenChange,
  server,
  isPending = false,
  errorMessage = null,
  onSubmit,
}: ServerFormDialogProps) {
  const isEdit = server !== null;
  const [form, setForm] = useState<FormState>(() =>
    server ? formFromServer(server) : emptyForm(),
  );
  const [touched, setTouched] = useState(false);

  const errors: Partial<Record<keyof FormState, string>> = {};
  if (!form.name.trim()) {
    errors.name = "Nama server wajib diisi.";
  }
  if (!form.host.trim()) {
    errors.host = "Host atau IP wajib diisi.";
  }
  const port = Number(form.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    errors.port = "Port harus berupa angka 1–65535.";
  }
  if (!form.username.trim()) {
    errors.username = "Username SSH wajib diisi.";
  }
  if (form.auth_type === "password" && !isEdit && !form.password) {
    errors.password = "Password wajib diisi untuk autentikasi password.";
  }
  if (form.auth_type === "private_key" && !isEdit && !form.private_key.trim()) {
    errors.private_key = "Private key wajib diisi untuk autentikasi private key.";
  }

  const isValid = Object.keys(errors).length === 0;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (!isValid) {
      return;
    }

    const values: ServerFormValues = {
      name: form.name.trim(),
      host: form.host.trim(),
      port,
      username: form.username.trim(),
      auth_type: form.auth_type,
      exporter_instance: form.exporter_instance.trim() || undefined,
    };

    if (form.auth_type === "password") {
      if (form.password) {
        values.password = form.password;
      }
    } else if (form.private_key.trim()) {
      values.private_key = form.private_key.trim();
    }

    onSubmit(values);
  }

  function showError(key: keyof FormState): string | undefined {
    if (!touched) {
      return undefined;
    }
    return errors[key];
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" data-testid="server-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Ubah server" : "Tambah server"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Kosongkan kredensial bila tidak ingin mengubahnya."
              : "Kredensial SSH dipakai untuk menguji koneksi server."}
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="server-name">Nama</Label>
              <Input
                id="server-name"
                value={form.name}
                onChange={(event) => update("name", event.target.value)}
                placeholder="Demo Server 1"
              />
              {showError("name") ? (
                <p className="text-xs text-destructive">{showError("name")}</p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="server-host">Host / IP</Label>
              <Input
                id="server-host"
                value={form.host}
                onChange={(event) => update("host", event.target.value)}
                placeholder="192.168.1.10"
              />
              {showError("host") ? (
                <p className="text-xs text-destructive">{showError("host")}</p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="server-port">Port SSH</Label>
              <Input
                id="server-port"
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(event) => update("port", event.target.value)}
              />
              {showError("port") ? (
                <p className="text-xs text-destructive">{showError("port")}</p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="server-username">Username SSH</Label>
              <Input
                id="server-username"
                value={form.username}
                onChange={(event) => update("username", event.target.value)}
                placeholder="deploy"
              />
              {showError("username") ? (
                <p className="text-xs text-destructive">{showError("username")}</p>
              ) : null}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="server-exporter">Exporter Prometheus</Label>
            <Input
              id="server-exporter"
              value={form.exporter_instance}
              onChange={(event) => update("exporter_instance", event.target.value)}
              placeholder="host.docker.internal:9100"
            />
            <p className="text-xs text-muted-foreground">
              Label instance Prometheus (job=node-exporter). Kosongkan bila belum ada.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label>Metode autentikasi</Label>
            <Select
              value={form.auth_type}
              onValueChange={(value) => update("auth_type", value as ServerAuthType)}
            >
              <SelectTrigger className="w-full" aria-label="Metode autentikasi">
                <SelectValue placeholder="Pilih metode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="password">Password</SelectItem>
                <SelectItem value="private_key">Private key</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {form.auth_type === "password" ? (
            <div className="space-y-1.5">
              <Label htmlFor="server-password">Password SSH</Label>
              <Input
                id="server-password"
                type="password"
                value={form.password}
                onChange={(event) => update("password", event.target.value)}
                placeholder={isEdit ? "Kosongkan bila tidak diubah" : "••••••••"}
              />
              {showError("password") ? (
                <p className="text-xs text-destructive">{showError("password")}</p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="server-private-key">Private key SSH</Label>
              <textarea
                id="server-private-key"
                value={form.private_key}
                onChange={(event) => update("private_key", event.target.value)}
                placeholder={
                  isEdit ? "Kosongkan bila tidak diubah" : "-----BEGIN OPENSSH PRIVATE KEY-----"
                }
                rows={4}
                className="w-full rounded-lg border bg-background px-2.5 py-2 font-mono text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              {showError("private_key") ? (
                <p className="text-xs text-destructive">{showError("private_key")}</p>
              ) : null}
            </div>
          )}

          {errorMessage ? (
            <p className="text-sm text-destructive" data-testid="server-form-error">
              {errorMessage}
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
            <Button type="submit" disabled={isPending} data-testid="server-form-submit">
              {isPending ? "Menyimpan…" : isEdit ? "Simpan perubahan" : "Tambah server"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
