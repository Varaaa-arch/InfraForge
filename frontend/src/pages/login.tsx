import { useMutation } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  Eye,
  EyeOff,
  Loader2,
  Rocket,
  ScrollText,
  ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { FullScreenLoader } from "@/components/full-screen-loader";
import { BrandMark } from "@/components/layout/app-sidebar";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";

const highlights = [
  {
    icon: Activity,
    title: "Monitoring terpusat",
    description: "Metrik Prometheus, Node Exporter, dan cAdvisor dalam satu dashboard.",
  },
  {
    icon: ScrollText,
    title: "Log real-time",
    description: "Telusuri log seluruh container lewat Loki dan WebSocket.",
  },
  {
    icon: Rocket,
    title: "Deployment otomatis",
    description: "Integrasi GitHub Actions, webhook, dan riwayat deployment.",
  },
  {
    icon: ShieldCheck,
    title: "Aman secara default",
    description: "JWT authentication dengan audit log untuk setiap aksi penting.",
  },
];

interface LoginLocationState {
  from?: { pathname?: string };
}

export function LoginPage() {
  const { login, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const mutation = useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      login(payload.username, payload.password),
  });

  const from = (location.state as LoginLocationState | null)?.from?.pathname ?? "/";

  if (status === "loading") {
    return <FullScreenLoader label="Memeriksa sesi…" />;
  }

  if (status === "authenticated") {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      return;
    }
    mutation.mutate(
      { username: username.trim(), password },
      { onSuccess: () => navigate(from, { replace: true }) },
    );
  };

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.error
        ? "Tidak dapat terhubung ke server. Coba lagi."
        : null;

  return (
    <div className="grid min-h-svh bg-background lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r bg-sidebar p-10 lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.04) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 -right-24 size-96 rounded-full bg-indigo-500/15 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-40 -left-24 size-96 rounded-full bg-emerald-500/10 blur-3xl"
        />

        <div className="relative flex items-center gap-2.5">
          <BrandMark />
          <div className="flex flex-col">
            <span className="text-sm font-semibold tracking-tight">InfraForge</span>
            <span className="text-[0.65rem] text-muted-foreground">Self-hosted DevOps Platform</span>
          </div>
        </div>

        <div className="relative max-w-md space-y-8">
          <div className="space-y-3">
            <h1 className="text-3xl font-semibold tracking-tight text-balance">
              Satu dashboard untuk seluruh infrastruktur Anda.
            </h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Deploy, monitor, dan telusuri log aplikasi tanpa berpindah-pindah tool.
              InfraForge menyatukan alur DevOps Anda dalam satu platform.
            </p>
          </div>

          <ul className="space-y-4">
            {highlights.map((item) => (
              <li key={item.title} className="flex gap-3">
                <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border bg-background/60">
                  <item.icon className="size-4" />
                </div>
                <div className="space-y-0.5">
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="text-xs leading-relaxed text-muted-foreground">{item.description}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-muted-foreground">
          Self-hosted · Open source · Apache License 2.0
        </p>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm space-y-6">
          <div className="flex items-center gap-2.5 lg:hidden">
            <BrandMark />
            <span className="text-sm font-semibold tracking-tight">InfraForge</span>
          </div>

          <div className="space-y-1.5">
            <h2 className="text-2xl font-semibold tracking-tight">Masuk ke InfraForge</h2>
            <p className="text-sm text-muted-foreground">
              Gunakan akun yang terdaftar untuk mengakses dashboard.
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
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
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
                "Masuk"
              )}
            </Button>
          </form>

          <Card className="border-dashed bg-muted/30">
            <CardHeader className="gap-1">
              <CardTitle className="text-sm">Belum punya akun?</CardTitle>
              <CardDescription className="text-xs">
                Pendaftaran akun dilakukan oleh administrator melalui API atau CLI InfraForge.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    </div>
  );
}
