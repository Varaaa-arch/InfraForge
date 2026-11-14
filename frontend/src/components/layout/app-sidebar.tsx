import {
  Activity,
  BellRing,
  Boxes,
  Hammer,
  LayoutDashboard,
  ScrollText,
  Server,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

interface NavItem {
  title: string;
  href: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const navSections: { label: string; items: NavItem[] }[] = [
  {
    label: "Overview",
    items: [{ title: "Overview", href: "/", icon: LayoutDashboard, end: true }],
  },
  {
    label: "Observability",
    items: [
      { title: "Monitoring", href: "/monitoring", icon: Activity },
      { title: "Logs", href: "/logs", icon: ScrollText },
      { title: "Alerts", href: "/alerts", icon: BellRing },
    ],
  },
  {
    label: "Infrastructure",
    items: [
      { title: "Servers", href: "/servers", icon: Server },
      { title: "Containers", href: "/containers", icon: Boxes },
    ],
  },
];

export function BrandMark() {
  return (
    <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
      <Hammer className="size-4" />
    </div>
  );
}

export function AppSidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2.5 border-b px-4">
        <BrandMark />
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-semibold tracking-tight">InfraForge</span>
          <span className="truncate text-[0.65rem] text-muted-foreground">DevOps Platform</span>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto p-3">
        {navSections.map((section) => (
          <div key={section.label}>
            <p className="mb-1.5 px-2 text-[0.65rem] font-medium tracking-wider text-muted-foreground uppercase">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavLink
                  key={item.href}
                  to={item.href}
                  end={item.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                        : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                    )
                  }
                >
                  <item.icon className="size-4" />
                  {item.title}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t p-3">
        <div className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2.5">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
          </span>
          <span className="text-xs text-muted-foreground">v0.1.0 · Self-hosted</span>
        </div>
      </div>
    </div>
  );
}
