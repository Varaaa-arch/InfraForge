import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { updateProfile } from "@/api/users";
import { Badge } from "@/components/ui/badge";
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
import { useAuth } from "@/hooks/use-auth";
import { usePermissions } from "@/hooks/use-permissions";

const dateFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "long",
});

export function ProfileTab() {
  const { user, refreshUser } = useAuth();
  const { label, role } = usePermissions();
  const [username, setUsername] = useState(user?.username ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      updateProfile({
        username: username.trim(),
        email: email.trim(),
        full_name: fullName.trim() ? fullName.trim() : "",
      }),
    onSuccess: async () => {
      await refreshUser();
      setFeedback({ type: "success", message: "Profil berhasil diperbarui." });
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message:
          error instanceof ApiError ? error.message : "Gagal memperbarui profil.",
      }),
  });

  if (!user) {
    return null;
  }

  const dirty =
    username.trim() !== user.username ||
    email.trim() !== user.email ||
    (fullName.trim() || "") !== (user.full_name ?? "");
  const canSubmit = dirty && username.trim().length >= 3 && email.includes("@");

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-sm">Profil</CardTitle>
        <CardDescription>
          Informasi akun Anda. Peran diatur oleh admin melalui tab Pengguna.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-sm">
          <span className="text-muted-foreground">Peran:</span>
          <Badge variant="outline" data-testid="profile-role">
            {label}
          </Badge>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">
            Bergabung {dateFormatter.format(new Date(user.created_at))}
          </span>
          {!user.is_active ? (
            <Badge variant="destructive" className="ml-auto">
              Nonaktif
            </Badge>
          ) : null}
        </div>

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
          <div className="space-y-1">
            <Label htmlFor="profile-username">Username</Label>
            <Input
              id="profile-username"
              data-testid="profile-username"
              value={username}
              minLength={3}
              maxLength={50}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="profile-email">Email</Label>
            <Input
              id="profile-email"
              data-testid="profile-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="profile-full-name">Nama lengkap</Label>
            <Input
              id="profile-full-name"
              data-testid="profile-full-name"
              value={fullName}
              maxLength={100}
              placeholder="Opsional"
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>

          <div className="sm:col-span-2">
            <Button
              type="submit"
              data-testid="profile-save"
              disabled={!canSubmit || mutation.isPending}
            >
              {mutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <CheckCircle2 className="size-4" />
              )}
              Simpan perubahan
            </Button>
          </div>
        </form>

        <p className="text-xs text-muted-foreground">
          Role saat ini: <span className="font-medium">{role}</span>.{" "}
          {role === "admin"
            ? "Anda dapat mengelola pengguna, server, dan channel notifikasi."
            : role === "developer"
              ? "Anda dapat deploy, mengelola project, env var, dan container."
              : "Anda memiliki akses baca untuk monitoring dan riwayat."}
        </p>

        {feedback ? (
          <div
            data-testid="profile-feedback"
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
