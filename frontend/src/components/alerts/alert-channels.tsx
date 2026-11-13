import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Loader2,
  Plus,
  Send,
  Trash2,
  Webhook,
  X,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import {
  createAlertChannel,
  deleteAlertChannel,
  fetchAlertChannels,
  testAlertChannel,
  updateAlertChannel,
} from "@/api/alerts";
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
import { cn } from "@/lib/utils";
import type {
  AlertChannel,
  AlertChannelCreatePayload,
  AlertChannelType,
} from "@/types/alert";

interface Feedback {
  type: "success" | "error";
  message: string;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function FeedbackBanner({ feedback }: { feedback: Feedback }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
        feedback.type === "success"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border-destructive/30 bg-destructive/10 text-destructive",
      )}
    >
      {feedback.type === "success" ? (
        <CheckCircle2 className="size-4 shrink-0" />
      ) : (
        <XCircle className="size-4 shrink-0" />
      )}
      {feedback.message}
    </div>
  );
}

function ChannelForm({ onCreated }: { onCreated: (channel: AlertChannel) => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AlertChannelType>("discord");
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [enabled, setEnabled] = useState(true);

  const mutation = useMutation({
    mutationFn: createAlertChannel,
    onSuccess: (channel) => {
      setName("");
      setDiscordWebhook("");
      setTelegramToken("");
      setTelegramChatId("");
      setEnabled(true);
      onCreated(channel);
    },
  });

  const canSubmit =
    name.trim().length > 0 &&
    (type === "discord"
      ? discordWebhook.trim().length > 0
      : telegramToken.trim().length > 0 && telegramChatId.trim().length > 0);

  const mutationError = mutation.error
    ? errorMessage(mutation.error, "Gagal menambah channel.")
    : null;

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-sm">Tambah channel notifikasi</CardTitle>
        <CardDescription>
          URL webhook dan bot token disimpan terenkripsi dan tidak pernah ditampilkan kembali.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canSubmit) {
              return;
            }

            const payload: AlertChannelCreatePayload = {
              name: name.trim(),
              type,
              enabled,
            };
            if (type === "discord") {
              payload.discord_webhook_url = discordWebhook.trim();
            } else {
              payload.telegram_bot_token = telegramToken.trim();
              payload.telegram_chat_id = telegramChatId.trim();
            }
            mutation.mutate(payload);
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="channel-name">Nama channel</Label>
            <Input
              id="channel-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Contoh: Tim Infra"
              maxLength={100}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="channel-type">Tipe</Label>
            <Select value={type} onValueChange={(value) => setType(value as AlertChannelType)}>
              <SelectTrigger id="channel-type" className="w-full" aria-label="Tipe channel">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="discord">Discord</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {type === "discord" ? (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="channel-discord-url">Discord webhook URL</Label>
              <Input
                id="channel-discord-url"
                type="url"
                value={discordWebhook}
                onChange={(event) => setDiscordWebhook(event.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                spellCheck={false}
              />
            </div>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="channel-telegram-token">Bot token</Label>
                <Input
                  id="channel-telegram-token"
                  type="password"
                  value={telegramToken}
                  onChange={(event) => setTelegramToken(event.target.value)}
                  placeholder="123456:ABC-DEF..."
                  spellCheck={false}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="channel-telegram-chat">Chat ID</Label>
                <Input
                  id="channel-telegram-chat"
                  value={telegramChatId}
                  onChange={(event) => setTelegramChatId(event.target.value)}
                  placeholder="-1001234567890"
                  spellCheck={false}
                />
              </div>
            </>
          )}

          <div className="flex items-center gap-2 sm:col-span-2">
            <Switch id="channel-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="channel-enabled">Aktifkan channel</Label>
          </div>

          {mutationError ? (
            <p className="text-sm text-destructive sm:col-span-2">{mutationError}</p>
          ) : null}

          <div className="sm:col-span-2">
            <Button type="submit" size="sm" disabled={!canSubmit || mutation.isPending}>
              {mutation.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Plus className="size-3.5" />
              )}
              Simpan channel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ChannelCard({
  channel,
  toggling,
  testing,
  deleting,
  onToggle,
  onTest,
  onDelete,
}: {
  channel: AlertChannel;
  toggling: boolean;
  testing: boolean;
  deleting: boolean;
  onToggle: (enabled: boolean) => void;
  onTest: () => void;
  onDelete: () => void;
}) {
  return (
    <Card size="sm" data-testid="channel-card">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <CardTitle className="truncate text-sm">{channel.name}</CardTitle>
          <CardDescription>
            <Badge
              variant="outline"
              className={
                channel.type === "discord"
                  ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400"
                  : "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400"
              }
            >
              {channel.type === "discord" ? "Discord" : "Telegram"}
            </Badge>
          </CardDescription>
        </div>
        <Switch
          checked={channel.enabled}
          disabled={toggling}
          onCheckedChange={onToggle}
          aria-label={`${channel.enabled ? "Nonaktifkan" : "Aktifkan"} channel ${channel.name}`}
        />
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {channel.type === "discord" ? (
            <Webhook className="size-3.5 shrink-0" />
          ) : (
            <Send className="size-3.5 shrink-0" />
          )}
          <span className="truncate">
            {channel.type === "discord"
              ? channel.has_discord_webhook
                ? "Webhook Discord terkonfigurasi"
                : "Webhook Discord belum diatur"
              : `Chat ID: ${channel.telegram_chat_id ?? "-"}`}
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onTest} disabled={testing}>
            {testing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Send className="size-3.5" />
            )}
            Test
          </Button>
          <Button variant="destructive" size="sm" onClick={onDelete} disabled={deleting}>
            {deleting ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Trash2 className="size-3.5" />
            )}
            Hapus
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function AlertChannels() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const channelsQuery = useQuery({
    queryKey: ["alert-channels"],
    queryFn: fetchAlertChannels,
  });

  const invalidateChannels = () =>
    queryClient.invalidateQueries({ queryKey: ["alert-channels"] });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateAlertChannel(id, { enabled }),
    onSuccess: (channel) => {
      setFeedback({
        type: "success",
        message: `Channel ${channel.name} ${channel.enabled ? "diaktifkan" : "dinonaktifkan"}.`,
      });
      void invalidateChannels();
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal memperbarui channel."),
      }),
  });

  const testMutation = useMutation({
    mutationFn: (channelId: number) => testAlertChannel(channelId),
    onSuccess: (_data, channelId) => {
      const name =
        channelsQuery.data?.find((channel) => channel.id === channelId)?.name ?? "channel";
      setFeedback({ type: "success", message: `Notifikasi uji terkirim ke ${name}.` });
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal mengirim notifikasi uji."),
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: (channelId: number) => deleteAlertChannel(channelId),
    onSuccess: (_data, channelId) => {
      const name =
        channelsQuery.data?.find((channel) => channel.id === channelId)?.name ?? "Channel";
      setFeedback({ type: "success", message: `${name} dihapus.` });
      void invalidateChannels();
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal menghapus channel."),
      }),
  });

  const togglingId = toggleMutation.isPending ? toggleMutation.variables?.id : undefined;
  const testingId = testMutation.isPending ? testMutation.variables : undefined;
  const deletingId = deleteMutation.isPending ? deleteMutation.variables : undefined;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-muted-foreground">
          Channel aktif menerima notifikasi untuk alert firing dan resolved.
        </p>
        <Button
          size="sm"
          variant={showForm ? "outline" : "default"}
          className="ml-auto"
          onClick={() => {
            setShowForm((current) => !current);
            setFeedback(null);
          }}
        >
          {showForm ? <X className="size-3.5" /> : <Plus className="size-3.5" />}
          {showForm ? "Tutup form" : "Tambah channel"}
        </Button>
      </div>

      {showForm ? (
        <ChannelForm
          onCreated={(channel) => {
            setFeedback({ type: "success", message: `Channel ${channel.name} ditambahkan.` });
            setShowForm(false);
            void invalidateChannels();
          }}
        />
      ) : null}

      {feedback ? <FeedbackBanner feedback={feedback} /> : null}

      {channelsQuery.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1].map((index) => (
            <Skeleton key={index} className="h-[150px] w-full rounded-xl" />
          ))}
        </div>
      ) : channelsQuery.isError ? (
        <Card size="sm">
          <CardContent className="flex flex-col items-center gap-2 p-6 text-center">
            <p className="text-sm text-destructive">
              {errorMessage(channelsQuery.error, "Tidak dapat memuat channel notifikasi.")}
            </p>
            <Button variant="outline" size="sm" onClick={() => void channelsQuery.refetch()}>
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : channelsQuery.data.length === 0 ? (
        <Card size="sm">
          <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
            <Webhook className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada channel notifikasi</p>
            <p className="text-xs text-muted-foreground">
              Tambahkan webhook Discord atau bot Telegram agar alert terkirim otomatis.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {channelsQuery.data.map((channel) => (
            <ChannelCard
              key={channel.id}
              channel={channel}
              toggling={togglingId === channel.id}
              testing={testingId === channel.id}
              deleting={deletingId === channel.id}
              onToggle={(enabled) => toggleMutation.mutate({ id: channel.id, enabled })}
              onTest={() => testMutation.mutate(channel.id)}
              onDelete={() => {
                if (window.confirm(`Hapus channel ${channel.name}?`)) {
                  deleteMutation.mutate(channel.id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
