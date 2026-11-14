import { Eye, EyeOff } from "lucide-react";
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
import { cn } from "@/lib/utils";
import type { EnvVarMasked } from "@/types/project";

const ENV_KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

export interface EnvVarFormValues {
  key?: string;
  value: string;
}

interface EnvVarFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  envVar: EnvVarMasked | null;
  isPending?: boolean;
  errorMessage?: string | null;
  onSubmit: (values: EnvVarFormValues) => void;
}

export function EnvVarFormDialog({
  open,
  onOpenChange,
  envVar,
  isPending = false,
  errorMessage = null,
  onSubmit,
}: EnvVarFormDialogProps) {
  const isEdit = envVar !== null;
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);
  const [touched, setTouched] = useState(false);

  const keyError = !isEdit && key.trim() && !ENV_KEY_PATTERN.test(key.trim())
    ? "Key hanya boleh huruf, angka, dan underscore (tidak diawali angka)."
    : null;
  const valueError = !value ? "Value tidak boleh kosong." : null;
  const isValid =
    !keyError && !valueError && (isEdit || (key.trim() !== "" && ENV_KEY_PATTERN.test(key.trim())));

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (!isValid) {
      return;
    }
    if (isEdit) {
      onSubmit({ value });
      return;
    }
    onSubmit({ key: key.trim().toUpperCase(), value });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="env-var-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Ubah environment variable" : "Tambah environment variable"}</DialogTitle>
          <DialogDescription>
            Nilai disimpan terenkripsi (Fernet) dan hanya ditampilkan dalam bentuk tersamar.
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="env-key">Key</Label>
            <Input
              id="env-key"
              value={isEdit ? envVar.key : key}
              onChange={(event) => setKey(event.target.value)}
              placeholder="DATABASE_URL"
              disabled={isEdit}
              className={cn(isEdit && "opacity-60")}
            />
            {isEdit ? (
              <p className="text-xs text-muted-foreground">
                Key tidak dapat diubah. Buat key baru bila perlu mengganti nama.
              </p>
            ) : keyError && touched ? (
              <p className="text-xs text-destructive">{keyError}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Huruf besar, angka, dan underscore. Disimpan sebagai uppercase.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="env-value">Value</Label>
            <div className="relative">
              <Input
                id="env-value"
                type={visible ? "text" : "password"}
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder={isEdit ? "Nilai baru" : "postgres://user:pass@host/db"}
                className="pr-9 font-mono"
                autoComplete="off"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="absolute top-1/2 right-1 -translate-y-1/2"
                aria-label={visible ? "Sembunyikan value" : "Tampilkan value"}
                onClick={() => setVisible((previous) => !previous)}
              >
                {visible ? <EyeOff /> : <Eye />}
              </Button>
            </div>
            {valueError && touched ? (
              <p className="text-xs text-destructive">{valueError}</p>
            ) : null}
          </div>

          {errorMessage ? (
            <p className="text-sm text-destructive" data-testid="env-var-form-error">
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
            <Button type="submit" disabled={isPending} data-testid="env-var-form-submit">
              {isPending ? "Menyimpan…" : isEdit ? "Simpan perubahan" : "Tambah variabel"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}