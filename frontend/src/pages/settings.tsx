import { BellRing, KeyRound, LockKeyhole, UserRound, Users } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { usePermissions } from "@/hooks/use-permissions";
import { ApiTokensCard } from "@/components/settings/api-tokens-card";
import { NotificationsTab } from "@/components/settings/notifications-tab";
import { ProfileTab } from "@/components/settings/profile-tab";
import { SecurityTab } from "@/components/settings/security-tab";
import { UsersTab } from "@/components/settings/users-tab";
import { cn } from "@/lib/utils";

type SettingsTab = "profile" | "security" | "tokens" | "users" | "notifications";

const TABS: { id: SettingsTab; label: string; icon: typeof UserRound }[] = [
  { id: "profile", label: "Profil", icon: UserRound },
  { id: "security", label: "Keamanan", icon: LockKeyhole },
  { id: "tokens", label: "API Token", icon: KeyRound },
  { id: "users", label: "Pengguna", icon: Users },
  { id: "notifications", label: "Notifikasi", icon: BellRing },
];

function isSettingsTab(value: string | null): value is SettingsTab {
  return TABS.some((tab) => tab.id === value);
}

export function SettingsPage() {
  const { isAdmin } = usePermissions();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const requestedTab: SettingsTab = isSettingsTab(requested) ? requested : "profile";
  const activeTab: SettingsTab =
    requestedTab === "users" && !isAdmin ? "profile" : requestedTab;

  const visibleTabs = TABS.filter((tab) => tab.id !== "users" || isAdmin);

  const selectTab = (tab: SettingsTab) => {
    const params = new URLSearchParams(searchParams);
    if (tab === "profile") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    setSearchParams(params, { replace: true });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Pengaturan</h1>
        <p className="text-sm text-muted-foreground">
          Kelola profil, keamanan akun, akses CLI/CI-CD, dan preferensi notifikasi.
        </p>
      </div>

      <div
        className="inline-flex flex-wrap items-center gap-1 rounded-lg border bg-muted/40 p-1"
        role="tablist"
        aria-label="Bagian pengaturan"
      >
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            data-testid={`settings-tab-${tab.id}`}
            onClick={() => selectTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
              activeTab === tab.id
                ? "bg-background font-medium text-foreground shadow-sm ring-1 ring-foreground/10"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <tab.icon className="size-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "profile" ? <ProfileTab /> : null}
      {activeTab === "security" ? <SecurityTab /> : null}
      {activeTab === "tokens" ? <ApiTokensCard /> : null}
      {activeTab === "users" && isAdmin ? <UsersTab /> : null}
      {activeTab === "notifications" ? <NotificationsTab /> : null}
    </div>
  );
}
