import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Send,
  MessagesSquare,
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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
import { usePermissions } from "@/hooks/use-permissions";
import { cn } from "@/lib/utils";
import type {
  AlertChannel,
  AlertChannelCreatePayload,
  AlertChannelType,
  AlertChannelUpdatePayload,
  AlertSeverity,
} from "@/types/alert";

interface Feedback {
  type: "success" | "error";
  message: string;
}

interface FormErrors {
  name?: string;
  secret?: string;
}

const TYPE_META: Record<
  AlertChannelType,
  { label: string; icon: typeof Webhook; badgeClassName: string }
> = {
  discord: {
    label: "Discord",
    icon: MessageSquare,
    badgeClassName:
      "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  },
  telegram: {
    label: "Telegram",
    icon: Send,
    badgeClassName:
      "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  },
  slack: {
    label: "Slack",
    icon: MessagesSquare,
    badgeClassName:
      "border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
};

const SEVERITY_META: Record<
  AlertSeverity,
  { label: string; description: string; badgeClassName: string }
> = {
  info: {
    label: "Semua severity",
    description: "Info, warning, dan critical",
    badgeClassName: "border-border text-muted-foreground",
  },
  warning: {
    label: "Warning ke atas",
    description: "Warning dan critical",
    badgeClassName:
      "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  critical: {
    label: "Hanya critical",
    description: "Critical saja",
    badgeClassName:
      "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function FeedbackBanner({ feedback }: { feedback: Feedback }) {
  return (
    <div
      data-testid="channel-feedback"
      role="status"
      className={cn(
        "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
        feedback.type === "success"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border-destructive/30 bg-destructive/10 text-destructive",
      )}
    >
      {feedback.type === "success" ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
      ) : (
        <XCircle className="mt-0.5 size-4 shrink-0" />
      )}
      <span className="min-w-0 break-words">{feedback.message}</span>
    </div>
  );
}

function ChannelTypeBadge({ type }: { type: AlertChannelType }) {
  const meta = TYPE_META[type];
  return (
    <Badge
      variant="outline"
      data-testid="channel-type-badge"
      className={cn("gap-1", meta.badgeClassName)}
    >
      <meta.icon className="size-3" />
      {meta.label}
    </Badge>
  );
}

function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const meta = SEVERITY_META[severity];
  return (
    <Badge
      variant="outline"
      data-testid="channel-severity-badge"
      className={meta.badgeClassName}
    >
      ≥ {meta.label}
    </Badge>
  );
}

function validateSecret(
  type: AlertChannelType,
  values: { discord: string; slack: string; token: string; chat: string },
): string | undefined {
  if (type === "telegram") {
    if (!values.token.trim()) {
      return "Bot token wajib diisi untuk channel Telegram.";
    }
    if (!values.chat.trim()) {
      return "Chat ID wajib diisi untuk channel Telegram.";
    }
    return undefined;
  }

  const url = type === "discord" ? values.discord.trim() : values.slack.trim();
  if (!url) {
    return `Webhook URL ${TYPE_META[type].label} wajib diisi.`;
  }
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    return "Webhook URL harus diawali http:// atau https://.";
  }
  return undefined;
}

function secretPayload(
  type: AlertChannelType,
  values: { discord: string; slack: string; token: string; chat: string },
): Pick<
  AlertChannelCreatePayload,
  | "discord_webhook_url"
  | "slack_webhook_url"
  | "telegram_bot_token"
  | "telegram_chat_id"
> {
  if (type === "discord") {
    return { discord_webhook_url: values.discord.trim() };
  }
  if (type === "slack") {
    return { slack_webhook_url: values.slack.trim() };
  }
  return {
    telegram_bot_token: values.token.trim(),
    telegram_chat_id: values.chat.trim(),
  };
}

function ChannelCreateForm({ onCreated }: { onCreated: (channel: AlertChannel) => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AlertChannelType>("discord");
  const [discordUrl, setDiscordUrl] = useState("");
  const [slackUrl, setSlackUrl] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [minSeverity, setMinSeverity] = useState<AlertSeverity>("warning");
  const [enabled, setEnabled] = useState(true);
  const [errors, setErrors] = useState<FormErrors>({});

  const mutation = useMutation({
    mutationFn: createAlertChannel,
    onSuccess: (channel) => {
      setName("");
      setDiscordUrl("");
      setSlackUrl("");
      setTelegramToken("");
      setTelegramChatId("");
      setErrors({});
      onCreated(channel);
    },
  });

  const mutationError = mutation.error
    ? errorMessage(mutation.error, "Gagal menambah channel.")
    : null;

  const submit = () => {
    const nextErrors: FormErrors = {};
    if (!name.trim()) {
      nextErrors.name = "Nama channel wajib diisi.";
    }
    const secretError = validateSecret(type, {
      discord: discordUrl,
      slack: slackUrl,
      token: telegramToken,
      chat: telegramChatId,
    });
    if (secretError) {
      nextErrors.secret = secretError;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    mutation.mutate({
      name: name.trim(),
      type,
      min_severity: minSeverity,
      enabled,
      ...secretPayload(type, {
        discord: discordUrl,
        slack: slackUrl,
        token: telegramToken,
        chat: telegramChatId,
      }),
    });
  };

  return (
    <Card size="sm" data-testid="channel-form">
      <CardHeader>
        <CardTitle className="text-sm">Tambah alert destination</CardTitle>
        <CardDescription>
          Kredensial disimpan terenkripsi (Fernet) dan tidak pernah ditampilkan kembali.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-2"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="channel-name">Nama channel</Label>
            <Input
              id="channel-name"
              data-testid="channel-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Contoh: Tim Infra"
              maxLength={100}
            />
            {errors.name ? (
              <p className="text-xs text-destructive">{errors.name}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="channel-type">Tipe</Label>
            <Select
              value={type}
              onValueChange={(value) => {
                setType(value as AlertChannelType);
                setErrors({});
              }}
            >
              <SelectTrigger
                id="channel-type"
                data-testid="channel-type"
                className="w-full"
                aria-label="Tipe channel"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="discord">Discord</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="slack">Slack</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {type === "discord" ? (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="channel-discord-url">Discord webhook URL</Label>
              <Input
                id="channel-discord-url"
                data-testid="channel-discord-url"
                type="url"
                value={discordUrl}
                onChange={(event) => setDiscordUrl(event.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                spellCheck={false}
              />
            </div>
          ) : type === "slack" ? (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="channel-slack-url">Slack incoming webhook URL</Label>
              <Input
                id="channel-slack-url"
                data-testid="channel-slack-url"
                type="url"
                value={slackUrl}
                onChange={(event) => setSlackUrl(event.target.value)}
                placeholder="https://hooks.slack.com/services/T000/B000/..."
                spellCheck={false}
              />
            </div>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="channel-telegram-token">Bot token</Label>
                <Input
                  id="channel-telegram-token"
                  data-testid="channel-telegram-token"
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
                  data-testid="channel-telegram-chat"
                  value={telegramChatId}
                  onChange={(event) => setTelegramChatId(event.target.value)}
                  placeholder="-1001234567890"
                  spellCheck={false}
                />
              </div>
            </>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="channel-min-severity">Kirim alert mulai dari</Label>
            <Select
              value={minSeverity}
              onValueChange={(value) => setMinSeverity(value as AlertSeverity)}
            >
              <SelectTrigger
                id="channel-min-severity"
                data-testid="channel-min-severity"
                className="w-full"
                aria-label="Minimum severity"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(SEVERITY_META) as AlertSeverity[]).map((severity) => (
                  <SelectItem key={severity} value={severity}>
                    {SEVERITY_META[severity].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {SEVERITY_META[minSeverity].description}
            </p>
          </div>

          <div className="flex items-center gap-2 sm:col-span-2">
            <Switch
              id="channel-enabled"
              data-testid="channel-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
            <Label htmlFor="channel-enabled">Aktifkan channel</Label>
          </div>

          {errors.secret ? (
            <p className="text-sm text-destructive sm:col-span-2" data-testid="channel-form-error">
              {errors.secret}
            </p>
          ) : null}
          {mutationError ? (
            <p className="text-sm text-destructive sm:col-span-2" data-testid="channel-form-error">
              {mutationError}
            </p>
          ) : null}

          <div className="sm:col-span-2">
            <Button
              type="submit"
              size="sm"
              disabled={mutation.isPending}
              data-testid="channel-submit"
            >
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

function ChannelEditDialog({
  channel,
  open,
  onOpenChange,
  isPending,
  error,
  onSubmit,
}: {
  channel: AlertChannel;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isPending: boolean;
  error: string | null;
  onSubmit: (payload: AlertChannelUpdatePayload) => void;
}) {
  const [name, setName] = useState(channel.name);
  const [minSeverity, setMinSeverity] = useState<AlertSeverity>(channel.min_severity);
  const [enabled, setEnabled] = useState(channel.enabled);
  const [secret, setSecret] = useState("");

  const secretLabel =
    channel.type === "discord"
      ? "Discord webhook URL baru"
      : channel.type === "slack"
        ? "Slack webhook URL baru"
        : "Bot token baru";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="channel-edit-dialog">
        <DialogHeader>
          <DialogTitle>Ubah alert destination</DialogTitle>
          <DialogDescription>
            Kosongkan kredensial jika tidak ingin mengganti nilai yang tersimpan.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            const payload: AlertChannelUpdatePayload = {
              name: name.trim(),
              min_severity: minSeverity,
              enabled,
            };
            if (secret.trim()) {
              if (channel.type === "discord") {
                payload.discord_webhook_url = secret.trim();
              } else if (channel.type === "slack") {
                payload.slack_webhook_url = secret.trim();
              } else {
                payload.telegram_bot_token = secret.trim();
              }
            }
            onSubmit(payload);
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="channel-edit-name">Nama channel</Label>
            <Input
              id="channel-edit-name"
              data-testid="channel-edit-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="channel-edit-severity">Kirim alert mulai dari</Label>
            <Select
              value={minSeverity}
              onValueChange={(value) => setMinSeverity(value as AlertSeverity)}
            >
              <SelectTrigger
                id="channel-edit-severity"
                data-testid="channel-edit-severity"
                className="w-full"
                aria-label="Minimum severity"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(SEVERITY_META) as AlertSeverity[]).map((severity) => (
                  <SelectItem key={severity} value={severity}>
                    {SEVERITY_META[severity].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="channel-edit-secret">{secretLabel}</Label>
            <Input
              id="channel-edit-secret"
              data-testid="channel-edit-secret"
              type="password"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              placeholder="Biarkan kosong untuk mempertahankan"
              spellCheck={false}
            />
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="channel-edit-enabled"
              data-testid="channel-edit-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
            <Label htmlFor="channel-edit-enabled">Aktifkan channel</Label>
          </div>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              Batal
            </Button>
            <Button type="submit" disabled={isPending} data-testid="channel-edit-submit">
              {isPending ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Simpan perubahan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChannelCard({
  channel,
  canManage,
  toggling,
  testing,
  editing,
  deleting,
  onToggle,
  onTest,
  onEdit,
  onDelete,
}: {
  channel: AlertChannel;
  canManage: boolean;
  toggling: boolean;
  testing: boolean;
  editing: boolean;
  deleting: boolean;
  onToggle: (enabled: boolean) => void;
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const description =
    channel.type === "discord"
      ? channel.has_discord_webhook
        ? "Webhook Discord terkonfigurasi"
        : "Webhook Discord belum diatur"
      : channel.type === "slack"
        ? channel.has_slack_webhook
          ? "Webhook Slack terkonfigurasi"
          : "Webhook Slack belum diatur"
        : `Chat ID: ${channel.telegram_chat_id ?? "-"}`;

  return (
    <Card size="sm" data-testid="channel-card">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <CardTitle className="truncate text-sm">{channel.name}</CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-1.5">
            <ChannelTypeBadge type={channel.type} />
            <SeverityBadge severity={channel.min_severity} />
          </CardDescription>
        </div>
        {canManage ? (
          <Switch
            data-testid="channel-toggle"
            checked={channel.enabled}
            disabled={toggling}
            onCheckedChange={onToggle}
            aria-label={`${channel.enabled ? "Nonaktifkan" : "Aktifkan"} channel ${channel.name}`}
          />
        ) : (
          <Badge variant="outline">{channel.enabled ? "Aktif" : "Nonaktif"}</Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Webhook className="size-3.5 shrink-0" />
          <span className="truncate">{description}</span>
        </p>

        {canManage ? (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onTest}
              disabled={testing}
              data-testid="channel-test"
            >
              {testing ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Send className="size-3.5" />
              )}
              Test notifikasi
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onEdit}
              disabled={editing}
              data-testid="channel-edit"
            >
              {editing ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Pencil className="size-3.5" />
              )}
              Ubah
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={onDelete}
              disabled={deleting}
              data-testid="channel-delete"
            >
              {deleting ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
              Hapus
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function AlertDestinations() {
  const queryClient = useQueryClient();
  const { isAdmin } = usePermissions();
  const [showForm, setShowForm] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [editing, setEditing] = useState<AlertChannel | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<AlertChannel | null>(null);

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
        channelsQuery.data?.find((channel) => channel.id === channelId)?.name ??
        "channel";
      setFeedback({
        type: "success",
        message: `Notifikasi uji terkirim ke ${name}.`,
      });
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal mengirim notifikasi uji."),
      }),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      channelId,
      payload,
    }: {
      channelId: number;
      payload: AlertChannelUpdatePayload;
    }) => updateAlertChannel(channelId, payload),
    onSuccess: (channel) => {
      setEditing(null);
      setEditError(null);
      setFeedback({
        type: "success",
        message: `Channel ${channel.name} diperbarui.`,
      });
      void invalidateChannels();
    },
    onError: (error) =>
      setEditError(errorMessage(error, "Gagal memperbarui channel.")),
  });

  const deleteMutation = useMutation({
    mutationFn: (channelId: number) => deleteAlertChannel(channelId),
    onSuccess: (_data, channelId) => {
      const name =
        channelsQuery.data?.find((channel) => channel.id === channelId)?.name ??
        "Channel";
      setDeleting(null);
      setFeedback({ type: "success", message: `${name} dihapus.` });
      void invalidateChannels();
    },
    onError: (error) => {
      setDeleting(null);
      setFeedback({
        type: "error",
        message: errorMessage(error, "Gagal menghapus channel."),
      });
    },
  });

  const togglingId = toggleMutation.isPending
    ? toggleMutation.variables?.id
    : undefined;
  const testingId = testMutation.isPending ? testMutation.variables : undefined;
  const editingId = editing?.id;
  const deletingId = deleteMutation.isPending
    ? deleteMutation.variables
    : undefined;

  const channels = channelsQuery.data ?? [];
  const enabledCount = channels.filter((channel) => channel.enabled).length;
  const typeCounts = (Object.keys(TYPE_META) as AlertChannelType[])
    .map((type) => ({
      type,
      count: channels.filter((channel) => channel.type === type).length,
    }))
    .filter((item) => item.count > 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start gap-2">
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">
            Tujuan notifikasi alert dari Alertmanager — Discord, Telegram, dan Slack.
            Routing mengikuti threshold severity tiap channel.
          </p>
          <div className="flex flex-wrap items-center gap-1.5" data-testid="channel-summary">
            <Badge variant="outline">
              {enabledCount} aktif dari {channels.length} channel
            </Badge>
            {typeCounts.map(({ type, count }) => (
              <Badge key={type} variant="outline" className={TYPE_META[type].badgeClassName}>
                {TYPE_META[type].label} {count}
              </Badge>
            ))}
          </div>
        </div>
        {isAdmin ? (
          <Button
            size="sm"
            variant={showForm ? "outline" : "default"}
            className="ml-auto"
            data-testid="channel-add-button"
            onClick={() => {
              setShowForm((current) => !current);
              setFeedback(null);
            }}
          >
            {showForm ? <X className="size-3.5" /> : <Plus className="size-3.5" />}
            {showForm ? "Tutup form" : "Tambah channel"}
          </Button>
        ) : (
          <p className="ml-auto text-xs text-muted-foreground">
            Hanya admin yang dapat mengubah alert destination.
          </p>
        )}
      </div>

      {showForm && isAdmin ? (
        <ChannelCreateForm
          onCreated={(channel) => {
            setFeedback({
              type: "success",
              message: `Channel ${channel.name} ditambahkan.`,
            });
            setShowForm(false);
            void invalidateChannels();
          }}
        />
      ) : null}

      {feedback ? <FeedbackBanner feedback={feedback} /> : null}

      {channelsQuery.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1].map((index) => (
            <Skeleton key={index} className="h-[170px] w-full rounded-xl" />
          ))}
        </div>
      ) : channelsQuery.isError ? (
        <Card size="sm">
          <CardContent className="flex flex-col items-center gap-2 p-6 text-center">
            <p className="text-sm text-destructive">
              {errorMessage(
                channelsQuery.error,
                "Tidak dapat memuat channel notifikasi.",
              )}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void channelsQuery.refetch()}
            >
              Coba lagi
            </Button>
          </CardContent>
        </Card>
      ) : channels.length === 0 ? (
        <Card size="sm" data-testid="channel-empty">
          <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
            <Webhook className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Belum ada alert destination</p>
            <p className="text-xs text-muted-foreground">
              Tambahkan webhook Discord, bot Telegram, atau webhook Slack agar alert
              terkirim otomatis sesuai severity.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {channels.map((channel) => (
            <ChannelCard
              key={channel.id}
              channel={channel}
              canManage={isAdmin}
              toggling={togglingId === channel.id}
              testing={testingId === channel.id}
              editing={editingId === channel.id && updateMutation.isPending}
              deleting={deletingId === channel.id}
              onToggle={(enabled) =>
                toggleMutation.mutate({ id: channel.id, enabled })
              }
              onTest={() => testMutation.mutate(channel.id)}
              onEdit={() => {
                setEditError(null);
                setEditing(channel);
              }}
              onDelete={() => setDeleting(channel)}
            />
          ))}
        </div>
      )}

      {editing ? (
        <ChannelEditDialog
          key={editing.id}
          channel={editing}
          open
          onOpenChange={(open) => {
            if (!open) {
              setEditing(null);
              setEditError(null);
            }
          }}
          isPending={updateMutation.isPending}
          error={editError}
          onSubmit={(payload) =>
            updateMutation.mutate({ channelId: editing.id, payload })
          }
        />
      ) : null}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        title="Hapus alert destination?"
        description={
          deleting
            ? `${deleting.name} akan dihapus permanen. Alert baru tidak lagi dikirim ke channel ini.`
            : undefined
        }
        confirmLabel="Hapus"
        variant="destructive"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deleting) {
            deleteMutation.mutate(deleting.id);
          }
        }}
      />
    </div>
  );
}
