import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { registerRequest } from "@/api/auth";
import { ApiError } from "@/api/client";
import { FullScreenLoader } from "@/components/full-screen-loader";
import { BrandMark } from "@/components/layout/app-sidebar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";

interface RegisterLocationState {
  from?: { pathname?: string };
}

interface RegisterInput {
  username: string;
  email: string;
  password: string;
}

export function RegisterPage() {
  const { login, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async (input: RegisterInput) => {
      await registerRequest(input);
      return login(input.username, input.password);
    },
  });

  const from = (location.state as RegisterLocationState | null)?.from?.pathname ?? "/";

  if (status === "loading") {
    return <FullScreenLoader label="Memeriksa sesi…" />;
  }

  if (status === "authenticated") {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);

    const trimmedUsername = username.trim();
    const trimmedEmail = email.trim();

    if (trimmedUsername.length < 3) {
      setFormError("Username minimal 3 karakter.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setFormError("Format email tidak valid.");
      return;
    }
    if (password.length < 8) {
      setFormError("Password minimal 8 karakter.");
      return;
    }
    if (password !== confirmPassword) {
      setFormError("Konfirmasi password tidak cocok.");
      return;
    }

    mutation.mutate(
      { username: trimmedUsername, email: trimmedEmail, password },
      { onSuccess: () => navigate(from, { replace: true }) },
    );
  };

  const errorMessage =
    formError ??
    (mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.error
        ? "Tidak dapat terhubung ke server. Coba lagi."
        : null);

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6 sm:p-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center gap-2.5">
          <BrandMark />
          <div className="flex flex-col">
            <span className="text-sm font-semibold tracking-tight">InfraForge</span>
            <span className="text-[0.65rem] text-muted-foreground">Self-hosted DevOps Platform</span>
          </div>
        </div>

        <div className="space-y-1.5">
          <h1 className="text-2xl font-semibold tracking-tight">Buat akun InfraForge</h1>
          <p className="text-sm text-muted-foreground">
            Akun pertama bisa langsung dibuat di sini. Setelah terdaftar kamu akan
            otomatis masuk ke dashboard.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              autoFocus
              spellCheck={false}
              placeholder="mis. zenit"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={mutation.isPending}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="nama@email.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={mutation.isPending}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder="Minimal 8 karakter"
                className="pr-10"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={mutation.isPending}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
                aria-label={showPassword ? "Sembunyikan password" : "Tampilkan password"}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirm-password">Konfirmasi password</Label>
            <Input
              id="confirm-password"
              name="confirm-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="Ulangi password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              disabled={mutation.isPending}
              required
            />
          </div>

          {errorMessage ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Memproses…
              </>
            ) : (
              "Daftar"
            )}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Sudah punya akun?{" "}
          <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
            Masuk
          </Link>
        </p>
      </div>
    </div>
  );
}
