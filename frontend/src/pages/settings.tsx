import { ApiTokensCard } from "@/components/settings/api-tokens-card";

export function SettingsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-xl font-semibold">Pengaturan</h1>
        <p className="text-sm text-muted-foreground">
          Kelola akses CLI/CI-CD dan preferensi akun Anda.
        </p>
      </div>

      <ApiTokensCard />
    </div>
  );
}
