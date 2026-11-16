import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, RotateCcw, Save, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import {
  deleteContainerPolicy,
  fetchContainerPolicy,
  saveContainerPolicy,
} from "@/api/container-policies";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type {
  ContainerPolicyDetail,
  ContainerPolicyUpsert,
  RestartPolicy,
} from "@/types/container";

interface PolicyTarget {
  id: string;
  name: string;
}

interface ContainerPolicyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  container: PolicyTarget | null;
  onSaved?: (message: string) => void;
  onError?: (message: string) => void;
}

interface FormState {
  cpu: string;
  memory: string;
  restartPolicy: RestartPolicy;
  autoHeal: boolean;
  threshold: string;
  maxRestarts: string;
  cooldown: string;
  applyNow: boolean;
}

const restartOptions: { value: RestartPolicy; label: string }[] = [
  { value: "no", label: "Tidak pernah" },
  { value: "always", label: "Selalu" },
  { value: "unless-stopped", label: "Kecuali dihentikan manual" },
  { value: "on-failure", label: "Saat gagal" },
];

function initialForm(detail: ContainerPolicyDetail): FormState {
  const policy = detail.policy;
  return {
    cpu: policy?.cpu_limit_cores ? String(policy.cpu_limit_cores) : "",
    memory: policy?.memory_limit_bytes
      ? String(Math.round(policy.memory_limit_bytes / (1024 * 1024)))
      : "",
    restartPolicy: (policy?.restart_policy ?? "no") as RestartPolicy,
    autoHeal: policy?.auto_heal_enabled ?? false,
    threshold: String(policy?.unhealthy_threshold ?? 3),
    maxRestarts: String(policy?.max_restarts ?? 3),
    cooldown: String(policy?.restart_cooldown_seconds ?? 300),
    applyNow: true,
  };
}

function formatBytes(value: number | null): string {
  if (!value) {
    return "Tanpa limit";
  }
  const mib = value / (1024 * 1024);
  return `${mib >= 1024 ? (mib / 1024).toFixed(1) + " GiB" : Math.round(mib) + " MiB"}`;
}

interface PolicyFormProps {
  detail: ContainerPolicyDetail;
  busy: boolean;
  error: string | null;
  onSave: (payload: ContainerPolicyUpsert) => void;
  onDelete: () => void;
  onCancel: () => void;
}

function PolicyForm({ detail, busy, error, onSave, onDelete, onCancel }: PolicyFormProps) {
  const [form, setForm] = useState<FormState>(() => initialForm(detail));
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit() {
    setLocalError(null);
    const cpu = form.cpu.trim() === "" ? null : Number(form.cpu);
    const memory = form.memory.trim() === "" ? null : Number(form.memory);
    const threshold = Number(form.threshold);
    const maxRestarts = Number(form.maxRestarts);
    const cooldown = Number(form.cooldown);

    if (cpu !== null && (!Number.isFinite(cpu) || cpu <= 0)) {
      setLocalError("CPU limit harus angka lebih dari 0.");
      return;
    }
    if (memory !== null && (!Number.isFinite(memory) || memory < 0)) {
      setLocalError("Memory limit harus angka 0 (tanpa limit) atau lebih.");
      return;
    }
    if (!Number.isInteger(threshold) || threshold < 1) {
      setLocalError("Ambang unhealthy minimal 1.");
      return;
    }
    if (!Number.isInteger(maxRestarts) || maxRestarts < 0) {
      setLocalError("Batas restart minimal 0.");
      return;
    }
    if (!Number.isInteger(cooldown) || cooldown < 0) {
      setLocalError("Cooldown minimal 0 detik.");
      return;
    }

    onSave({
      cpu_limit_cores: cpu,
      memory_limit_mib: memory,
      restart_policy: form.restartPolicy,
      auto_heal_enabled: form.autoHeal,
      unhealthy_threshold: threshold,
      max_restarts: maxRestarts,
      restart_cooldown_seconds: cooldown,
      apply_now: form.applyNow,
    });
  }

  const shownError = localError ?? error;

  return (
    <>
      <div className="space-y-4">
        <div
          className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
          data-testid="container-policy-current"
        >
          <span>Aktif di Docker:</span>
          <Badge variant="outline" className="font-mono text-[10px]">
            CPU {detail.effective.cpu_limit_cores ?? "tanpa limit"}
          </Badge>
          <Badge variant="outline" className="font-mono text-[10px]">
            RAM {formatBytes(detail.effective.memory_limit_bytes)}
          </Badge>
          <Badge variant="outline" className="font-mono text-[10px]">
            Restart {detail.effective.restart_policy}
          </Badge>
          {detail.health ? (
            <Badge variant="outline" className="text-[10px]">
              Health {detail.health}
            </Badge>
          ) : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="container-policy-cpu">Limit CPU (cores)</Label>
            <Input
              id="container-policy-cpu"
              type="number"
              min="0"
              step="0.1"
              placeholder="Kosong = tanpa limit"
              value={form.cpu}
              onChange={(event) => update("cpu", event.target.value)}
              data-testid="container-policy-cpu"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="container-policy-memory">Limit memory (MiB)</Label>
            <Input
              id="container-policy-memory"
              type="number"
              min="0"
              step="1"
              placeholder="0 = tanpa limit"
              value={form.memory}
              onChange={(event) => update("memory", event.target.value)}
              data-testid="container-policy-memory"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="container-policy-restart">Restart policy Docker</Label>
          <Select
            value={form.restartPolicy}
            onValueChange={(value) => update("restartPolicy", value as RestartPolicy)}
          >
            <SelectTrigger
              id="container-policy-restart"
              className="w-full"
              data-testid="container-policy-restart"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {restartOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-3 rounded-lg border p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-0.5">
              <Label htmlFor="container-policy-autoheal">Auto-healing</Label>
              <p className="text-xs text-muted-foreground">
                Pantau healthcheck dan restart otomatis saat unhealthy.
              </p>
            </div>
            <Switch
              id="container-policy-autoheal"
              checked={form.autoHeal}
              onCheckedChange={(checked) => update("autoHeal", checked)}
              data-testid="container-policy-autoheal"
            />
          </div>

          {form.autoHeal ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="container-policy-threshold">Ambang unhealthy</Label>
                <Input
                  id="container-policy-threshold"
                  type="number"
                  min="1"
                  value={form.threshold}
                  onChange={(event) => update("threshold", event.target.value)}
                  data-testid="container-policy-threshold"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="container-policy-max-restarts">Maks. restart</Label>
                <Input
                  id="container-policy-max-restarts"
                  type="number"
                  min="0"
                  value={form.maxRestarts}
                  onChange={(event) => update("maxRestarts", event.target.value)}
                  data-testid="container-policy-max-restarts"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="container-policy-cooldown">Cooldown (detik)</Label>
                <Input
                  id="container-policy-cooldown"
                  type="number"
                  min="0"
                  value={form.cooldown}
                  onChange={(event) => update("cooldown", event.target.value)}
                  data-testid="container-policy-cooldown"
                />
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="space-y-0.5">
            <Label htmlFor="container-policy-apply-now">Terapkan sekarang</Label>
            <p className="text-xs text-muted-foreground">
              Kirim limit ke container yang sedang berjalan.
            </p>
          </div>
          <Switch
            id="container-policy-apply-now"
            checked={form.applyNow}
            onCheckedChange={(checked) => update("applyNow", checked)}
            data-testid="container-policy-apply-now"
          />
        </div>

        {shownError ? (
          <div
            className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400"
            data-testid="container-policy-error"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <p>{shownError}</p>
          </div>
        ) : null}
      </div>

      <DialogFooter className="sm:justify-between">
        <div>
          {detail.policy ? (
            confirmDelete ? (
              <div className="flex items-center gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={onDelete}
                  disabled={busy}
                  data-testid="container-policy-delete-confirm"
                >
                  {busy ? <Loader2Icon className="animate-spin" /> : null}
                  Yakin hapus
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmDelete(false)}
                  disabled={busy}
                >
                  Batal
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDelete(true)}
                disabled={busy}
                data-testid="container-policy-delete"
              >
                <RotateCcw />
                Hapus policy
              </Button>
            )
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Batal
          </Button>
          <Button onClick={submit} disabled={busy} data-testid="container-policy-save">
            {busy ? <Loader2Icon className="animate-spin" /> : <Save />}
            Simpan
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}

export function ContainerPolicyDialog({
  open,
  onOpenChange,
  container,
  onSaved,
  onError,
}: ContainerPolicyDialogProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["container-policy", container?.id],
    queryFn: () => fetchContainerPolicy(container!.id),
    enabled: open && container !== null,
    retry: 1,
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["container-policies"] });
    void queryClient.invalidateQueries({ queryKey: ["container-policy", container?.id] });
    void queryClient.invalidateQueries({ queryKey: ["containers"] });
  }

  const saveMutation = useMutation({
    mutationFn: (payload: ContainerPolicyUpsert) =>
      saveContainerPolicy(container!.id, payload),
    onSuccess: (result) => {
      invalidate();
      onSaved?.(result.message);
      onOpenChange(false);
    },
    onError: (mutationError) => {
      const message =
        mutationError instanceof ApiError
          ? mutationError.message
          : "Gagal menyimpan policy container.";
      setError(message);
      onError?.(message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteContainerPolicy(container!.id),
    onSuccess: (result) => {
      invalidate();
      onSaved?.(result.message);
      onOpenChange(false);
    },
    onError: (mutationError) => {
      const message =
        mutationError instanceof ApiError
          ? mutationError.message
          : "Gagal menghapus policy container.";
      setError(message);
      onError?.(message);
    },
  });

  const detail = detailQuery.data;
  const busy = saveMutation.isPending || deleteMutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          setError(null);
        }
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className="sm:max-w-xl" data-testid="container-policy-dialog">
        <DialogHeader>
          <DialogTitle>Resource & auto-healing</DialogTitle>
          <DialogDescription>
            Atur limit CPU/memory dan restart otomatis untuk{" "}
            <span className="font-medium text-foreground">{container?.name}</span>.
            Limit yang sudah terpasang baru hilang saat container dibuat ulang.
          </DialogDescription>
        </DialogHeader>

        {detailQuery.isPending ? (
          <div className="space-y-2">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-9 w-full rounded-md" />
            ))}
          </div>
        ) : detailQuery.error ? (
          <div
            className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400"
            data-testid="container-policy-error"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <p>
              {detailQuery.error instanceof ApiError
                ? detailQuery.error.message
                : "Gagal memuat policy container."}
            </p>
          </div>
        ) : detail ? (
          <PolicyForm
            detail={detail}
            busy={busy}
            error={error}
            onSave={(payload) => {
              setError(null);
              saveMutation.mutate(payload);
            }}
            onDelete={() => deleteMutation.mutate()}
            onCancel={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
