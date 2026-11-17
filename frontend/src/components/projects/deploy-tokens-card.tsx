import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  Trash2,
  Webhook,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { ApiError, API_BASE_URL } from "@/api/client";
import {
  createDeployToken,
  fetchDeployTokens,
  revokeDeployToken,
} from "@/api/deploy-tokens";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { DeploymentToken, DeploymentTokenCreated } from "@/types/deployment";

const dateFormatter = new Intl.DateTimeFormat("id-ID", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  return dateFormatter.format(new Date(iso));
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function tokenStatus(token: DeploymentToken): "active" | "revoked" | "expired" {
  if (token.revoked_at) {
    return "revoked";
  }
  if (token.expires_at && new Date(token.expires_at).getTime() <= Date.now()) {
    return "expired";
  }
  return "active";
}

const STATUS_LABEL: Record<ReturnType<typeof tokenStatus>, string> = {
  active: "Aktif",
  revoked: "Dicabut",
  expired: "Kedaluwarsa",
};

const CURL_SNIPPET = [
  `curl -fsS -X POST "${API_BASE_URL}/deploy/trigger/<token>" \\`,
  '  -H "Content-Type: application/json" \\',
  `  -d '{"branch":"main"}'`,
].join("\n");

const GITHUB_ACTIONS_SNIPPET = [
  "- name: Deploy via InfraForge",
  "  run: |",
  '    curl -fsS -X POST "${{ secrets.INFRAFORGE_TRIGGER_URL }}" \\',
  '      -H "Content-Type: application/json" \\',
  `      -d '{"branch":"\${{ github.ref_name }}"}'`,
].join("\n");

function Feedback({ type, message }: { type: "success" | "error"; message: string }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
        type === "success"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border-destructive/30 bg-destructive/10 text-destructive",
      )}
    >
      {type === "success" ? (
        <CheckCircle2 className="size-4 shrink-0" />
      ) : (
        <XCircle className="size-4 shrink-0" />
      )}
      {message}
    </div>
  );
}

interface DeployTokensCardProps {
  projectId: number;
  canManage: boolean;
}

export function DeployTokensCard({ projectId, canManage }: DeployTokensCardProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [expiry, setExpiry] = useState("90");
  const [created, setCreated] = useState<DeploymentTokenCreated | null>(null);
  const [revoking, setRevoking] = useState<DeploymentToken | null>(null);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const tokensQuery = useQuery({
    queryKey: ["deploy-tokens", projectId],
    queryFn: () => fetchDeployTokens(projectId),
    enabled: canManage,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["deploy-tokens", projectId] });

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; expiresInDays?: number }) =>
      createDeployToken(projectId, {
        name: payload.name,
        expires_in_days: payload.expiresInDays,
      }),
    onSuccess: (token) => {
      setCreated(token);
      setName("");
      setExpiry("90");
      setFeedback(null);
      void invalidate();
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal membuat deployment token."),
      }),
  });

  const revokeMutation = useMutation({
    mutationFn: (tokenId: number) => revokeDeployToken(projectId, tokenId),
    onSuccess: (_data, tokenId) => {
      const revokedName =
        tokensQuery.data?.find((token) => token.id === tokenId)?.name ?? "Token";
      setFeedback({ type: "success", message: `${revokedName} dicabut.` });
      setRevoking(null);
      void invalidate();
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal mencabut token."),
      }),
  });

  const tokens = tokensQuery.data ?? [];
  const activeTokens = tokens.filter((token) => tokenStatus(token) === "active");
  const canSubmit = name.trim().length > 0 && !createMutation.isPending;

  const copyText = async (text: string, message: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setFeedback({ type: "success", message });
    } catch {
      setFeedback({
        type: "error",
        message: "Gagal menyalin otomatis — salin teks secara manual.",
      });
    }
  };

  return (
    <div className="space-y-4" data-testid="deploy-tokens-card">
      <Card size="sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <KeyRound className="size-4" />
            Deployment Token (CI/CD)
          </CardTitle>
          <CardDescription>
            Token khusus project untuk memicu deployment dari GitHub Actions atau
            pipeline lain lewat endpoint <code>POST /deploy/trigger/&lt;token&gt;</code>.
            Token hanya ditampilkan sekali saat dibuat — InfraForge menyimpan hash.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {!canManage ? (
            <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
              Hanya pemilik project dengan peran developer/admin yang dapat mengelola
              deployment token.
            </p>
          ) : (
            <>
              <form
                className="grid gap-3 sm:grid-cols-[1fr_150px_auto] sm:items-end"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!canSubmit) {
                    return;
                  }
                  createMutation.mutate({
                    name: name.trim(),
                    expiresInDays: expiry === "never" ? undefined : Number(expiry),
                  });
                }}
              >
                <div className="space-y-1">
                  <Label htmlFor="deploy-token-name">Nama token</Label>
                  <Input
                    id="deploy-token-name"
                    data-testid="deploy-token-name"
                    placeholder="github-actions-production"
                    value={name}
                    maxLength={100}
                    onChange={(event) => setName(event.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="deploy-token-expiry">Masa berlaku</Label>
                  <Select value={expiry} onValueChange={setExpiry}>
                    <SelectTrigger
                      id="deploy-token-expiry"
                      data-testid="deploy-token-expiry"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="30">30 hari</SelectItem>
                      <SelectItem value="90">90 hari</SelectItem>
                      <SelectItem value="365">1 tahun</SelectItem>
                      <SelectItem value="never">Tanpa kedaluwarsa</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <Button
                  type="submit"
                  data-testid="deploy-token-create"
                  disabled={!canSubmit}
                >
                  {createMutation.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Plus className="size-4" />
                  )}
                  Buat token
                </Button>
              </form>

              {feedback ? (
                <Feedback type={feedback.type} message={feedback.message} />
              ) : null}

              {tokensQuery.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : tokens.length === 0 ? (
                <p
                  className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground"
                  data-testid="deploy-token-empty"
                >
                  Belum ada deployment token. Buat token untuk mulai deploy dari CI/CD.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Nama</TableHead>
                        <TableHead>Prefix</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Kedaluwarsa</TableHead>
                        <TableHead>Terakhir dipakai</TableHead>
                        <TableHead className="text-right">Aksi</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tokens.map((token) => {
                        const status = tokenStatus(token);
                        return (
                          <TableRow key={token.id} data-testid="deploy-token-row">
                            <TableCell className="font-medium">{token.name}</TableCell>
                            <TableCell>
                              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                                {token.prefix}…
                              </code>
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant={status === "active" ? "default" : "secondary"}
                                className={cn(
                                  status === "active" &&
                                    "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
                                )}
                              >
                                {STATUS_LABEL[status]}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {token.expires_at
                                ? formatDateTime(token.expires_at)
                                : "Tidak ada"}
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {formatDateTime(token.last_used_at)}
                            </TableCell>
                            <TableCell className="text-right">
                              {status === "active" ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  data-testid="deploy-token-revoke"
                                  onClick={() => setRevoking(token)}
                                >
                                  <Trash2 className="size-3.5" />
                                  Cabut
                                </Button>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}

              <p className="text-xs text-muted-foreground">
                {activeTokens.length} token aktif. Deployment yang dipicu token tercatat
                di tab <span className="font-medium">Deployment</span> dengan pemicu
                &quot;CI Token&quot;.
              </p>
            </>
          )}
        </CardContent>
      </Card>

      {canManage ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Webhook className="size-4" />
              Contoh pemakaian
            </CardTitle>
            <CardDescription>
              Salin salah satu snippet berikut. Ganti <code>&lt;token&gt;</code> dengan
              deployment token project; simpan sebagai secret di repository.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">curl</p>
              <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 text-xs">
                <code data-testid="deploy-token-curl-snippet">{CURL_SNIPPET}</code>
              </pre>
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">
                GitHub Actions
              </p>
              <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 text-xs">
                <code data-testid="deploy-token-actions-snippet">
                  {GITHUB_ACTIONS_SNIPPET}
                </code>
              </pre>
              <p className="text-xs text-muted-foreground">
                Isi secret <code>INFRAFORGE_TRIGGER_URL</code> dengan{" "}
                <code>
                  {API_BASE_URL}/deploy/trigger/&lt;token&gt;
                </code>
                . Project dengan lebih dari satu aplikasi perlu mengirim{" "}
                <code>application_id</code> di body.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Dialog open={created !== null} onOpenChange={(open) => !open && setCreated(null)}>
        <DialogContent data-testid="deploy-token-created-dialog">
          <DialogHeader>
            <DialogTitle>Deployment token dibuat</DialogTitle>
            <DialogDescription>
              Salin token sekarang. Untuk alasan keamanan, token lengkap tidak akan
              ditampilkan lagi setelah dialog ini ditutup.
            </DialogDescription>
          </DialogHeader>

          {created ? (
            <div className="space-y-3">
              <div className="rounded-lg border bg-muted/50 p-3">
                <code
                  className="block break-all text-xs"
                  data-testid="deploy-token-plaintext"
                >
                  {created.token}
                </code>
              </div>
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  Contoh trigger
                </p>
                <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 text-xs">
                  <code data-testid="deploy-token-created-curl">
                    {`curl -fsS -X POST "${API_BASE_URL}/deploy/trigger/${created.token}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"branch":"main"}'`}
                  </code>
                </pre>
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              variant="outline"
              data-testid="deploy-token-copy"
              onClick={() =>
                created &&
                void copyText(created.token, "Token disalin ke clipboard.")
              }
            >
              <Copy className="size-4" />
              Salin token
            </Button>
            <Button onClick={() => setCreated(null)}>Selesai</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={revoking !== null} onOpenChange={(open) => !open && setRevoking(null)}>
        <DialogContent data-testid="deploy-token-revoke-dialog">
          <DialogHeader>
            <DialogTitle>Cabut deployment token?</DialogTitle>
            <DialogDescription>
              Token <span className="font-medium">{revoking?.name}</span> tidak akan bisa
              memicu deployment lagi. Deployment yang sedang berjalan tidak dibatalkan.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevoking(null)}>
              Batal
            </Button>
            <Button
              variant="destructive"
              data-testid="deploy-token-revoke-confirm"
              disabled={revokeMutation.isPending}
              onClick={() => revoking && revokeMutation.mutate(revoking.id)}
            >
              {revokeMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              Cabut token
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
