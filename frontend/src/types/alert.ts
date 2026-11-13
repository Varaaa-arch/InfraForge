export type AlertStatus = "firing" | "resolved";

export type AlertChannelType = "discord" | "telegram";

export interface AlertEvent {
  id: number;
  fingerprint: string;
  alert_name: string;
  status: AlertStatus;
  severity: string;
  summary: string | null;
  description: string | null;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  starts_at: string;
  ends_at: string | null;
  created_at: string;
}

export interface AlertChannel {
  id: number;
  name: string;
  type: AlertChannelType;
  enabled: boolean;
  has_discord_webhook: boolean;
  has_telegram_bot_token: boolean;
  telegram_chat_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertChannelCreatePayload {
  name: string;
  type: AlertChannelType;
  discord_webhook_url?: string;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  enabled?: boolean;
}

export interface AlertChannelUpdatePayload {
  name?: string;
  discord_webhook_url?: string;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  enabled?: boolean;
}
