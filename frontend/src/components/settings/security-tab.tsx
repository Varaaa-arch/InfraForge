import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Loader2, XCircle } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { changePassword } from "@/api/users";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SecurityTab() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const mutation = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: (data) => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setFeedback({ type: "success", message: data.message });
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message:
          error instanceof ApiError ? error.message : "Gagal mengubah password.",
      }),
  });

  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;
  const canSubmit =
    currentPassword.length > 0 &&
    newPassword.length >= 8 &&
    newPassword === confirmPassword;

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <KeyRound className="size-4" />
          Keamanan
        </CardTitle>
        <CardDescription>
          Ganti password akun. Minimal 8 karakter. Sesi login di perangkat lain tidak
          otomatis berakhir.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canSubmit) {
              return;
            }
            mutation.mutate();
          }}
        >
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="security-current">Password saat ini</Label>
            <Input
              id="security-current"
              data-testid="security-current"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="security-new">Password baru</Label>
            <Input
              id="security-new"
              data-testid="security-new"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              minLength={8}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="security-confirm">Ulangi password baru</Label>
            <Input
              id="security-confirm"
              data-testid="security-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </div>

          {mismatch ? (
            <p className="text-xs text-destructive sm:col-span-2">
              Konfirmasi password tidak cocok.
            </p>
          ) : null}

          <div className="sm:col-span-2">
            <Button
              type="submit"
              data-testid="security-save"
              disabled={!canSubmit || mutation.isPending}
            >
              {mutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <KeyRound className="size-4" />
              )}
              Ubah password
            </Button>
          </div>
        </form>

        {feedback ? (
          <div
            data-testid="security-feedback"
            className={
              feedback.type === "success"
                ? "flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400"
                : "flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            }
          >
            {feedback.type === "success" ? (
              <CheckCircle2 className="size-4 shrink-0" />
            ) : (
              <XCircle className="size-4 shrink-0" />
            )}
            {feedback.message}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
