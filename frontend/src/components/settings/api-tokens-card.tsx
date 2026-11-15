import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, KeyRound, Loader2, Plus, Trash2, XCircle } from "lucide-react";
import { useState } from "react";

import { createApiToken, fetchApiTokens, revokeApiToken } from "@/api/api-tokens";
import { ApiError } from "@/api/client";
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
import type { ApiToken, ApiTokenCreated, ApiTokenScope } from "@/types/api-token";

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

function tokenStatus(token: ApiToken): "active" | "revoked" | "expired" {
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

export function ApiTokensCard() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [scopeMode, setScopeMode] = useState<"full" | "read">("full");
  const [expiry, setExpiry] = useState("90");
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);
  const [revoking, setRevoking] = useState<ApiToken | null>(null);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const tokensQuery = useQuery({
    queryKey: ["api-tokens"],
    queryFn: fetchApiTokens,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["api-tokens"] });

  const createMutation = useMutation({
    mutationFn: createApiToken,
    onSuccess: (token) => {
      setCreated(token);
      setName("");
      setScopeMode("full");
      setExpiry("90");
      setFeedback(null);
      void invalidate();
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal membuat token."),
      }),
  });

  const revokeMutation = useMutation({
    mutationFn: (tokenId: number) => revokeApiToken(tokenId),
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

  const copyToken = async (token: string) => {
    try {
      await navigator.clipboard.writeText(token);
      setFeedback({ type: "success", message: "Token disalin ke clipboard." });
    } catch {
      setFeedback({
        type: "error",
        message: "Gagal menyalin otomatis — salin token secara manual.",
      });
    }
  };

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <KeyRound className="size-4" />
          API Token
        </CardTitle>
        <CardDescription>
          Token untuk akses CLI dan pipeline CI/CD. Token hanya ditampilkan sekali saat
          dibuat — InfraForge menyimpan hash, bukan token aslinya.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_170px_150px_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canSubmit) {
              return;
            }
            const scopes: ApiTokenScope[] | undefined =
              scopeMode === "read" ? ["read"] : undefined;
            const expiresInDays = expiry === "never" ? undefined : Number(expiry);
            createMutation.mutate({
              name: name.trim(),
              scopes,
              expires_in_days: expiresInDays,
            });
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="api-token-name">Nama token</Label>
            <Input
              id="api-token-name"
              data-testid="api-token-name"
              placeholder="deploy-cli"
              value={name}
              maxLength={100}
              onChange={(event) => setName(event.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="api-token-scope">Akses</Label>
            <Select
              value={scopeMode}
              onValueChange={(value) => setScopeMode(value as "full" | "read")}
            >
              <SelectTrigger id="api-token-scope" data-testid="api-token-scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full">Baca & tulis</SelectItem>
                <SelectItem value="read">Hanya baca</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="api-token-expiry">Masa berlaku</Label>
            <Select value={expiry} onValueChange={setExpiry}>
              <SelectTrigger id="api-token-expiry" data-testid="api-token-expiry">
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
            data-testid="api-token-create"
            disabled={!canSubmit}
          >
            {createMutation.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Plus className="size-4" />
            )}
            Buat
          </Button>
        </form>

        {feedback ? <Feedback type={feedback.type} message={feedback.message} /> : null}

        {tokensQuery.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : tokens.length === 0 ? (
          <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            Belum ada token. Buat token pertama Anda untuk mulai memakai CLI/CI-CD.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nama</TableHead>
                  <TableHead>Prefix</TableHead>
                  <TableHead>Akses</TableHead>
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
                    <TableRow key={token.id} data-testid="api-token-row">
                      <TableCell className="font-medium">{token.name}</TableCell>
                      <TableCell>
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                          {token.prefix}…
                        </code>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {token.scopes === null ? "Baca & tulis" : "Hanya baca"}
                        </Badge>
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
                        {token.expires_at ? formatDateTime(token.expires_at) : "Tidak ada"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(token.last_used_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {status === "active" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid="api-token-revoke"
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
          {activeTokens.length} token aktif. Gunakan header{" "}
          <code className="rounded bg-muted px-1.5 py-0.5">
            Authorization: Bearer &lt;token&gt;
          </code>{" "}
          pada CLI atau pipeline.
        </p>
      </CardContent>

      <Dialog open={created !== null} onOpenChange={(open) => !open && setCreated(null)}>
        <DialogContent data-testid="api-token-created-dialog">
          <DialogHeader>
            <DialogTitle>Token baru dibuat</DialogTitle>
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
                  data-testid="api-token-plaintext"
                >
                  {created.token}
                </code>
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>Nama: {created.name}</span>
                <span>·</span>
                <span>
                  Akses: {created.scopes === null ? "baca & tulis" : "hanya baca"}
                </span>
                <span>·</span>
                <span>
                  Kedaluwarsa:{" "}
                  {created.expires_at ? formatDateTime(created.expires_at) : "tidak ada"}
                </span>
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              variant="outline"
              data-testid="api-token-copy"
              onClick={() => created && void copyToken(created.token)}
            >
              <Copy className="size-4" />
              Salin token
            </Button>
            <Button onClick={() => setCreated(null)}>Selesai</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={revoking !== null} onOpenChange={(open) => !open && setRevoking(null)}>
        <DialogContent data-testid="api-token-revoke-dialog">
          <DialogHeader>
            <DialogTitle>Cabut token?</DialogTitle>
            <DialogDescription>
              Token <span className="font-medium">{revoking?.name}</span> tidak akan bisa
              dipakai lagi untuk autentikasi. Tindakan ini tidak dapat dibatalkan.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevoking(null)}>
              Batal
            </Button>
            <Button
              variant="destructive"
              data-testid="api-token-revoke-confirm"
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
    </Card>
  );
}
