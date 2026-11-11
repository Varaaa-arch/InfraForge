import { Menu } from "lucide-react";
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { StatusIndicator } from "@/components/layout/status-indicator";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const pageTitles: Record<string, string> = {
  "/": "Dashboard",
  "/logs": "Logs",
};

export function AppLayout() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const title = pageTitles[location.pathname] ?? "InfraForge";

  return (
    <div className="flex min-h-svh bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r bg-sidebar lg:block">
        <AppSidebar />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur-sm sm:px-6">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon-sm" className="lg:hidden" aria-label="Buka menu">
                <Menu className="size-4" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 gap-0 p-0">
              <SheetTitle className="sr-only">Navigasi utama</SheetTitle>
              <SheetDescription className="sr-only">
                Menu navigasi untuk berpindah halaman.
              </SheetDescription>
              <AppSidebar onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>

          <div className="flex min-w-0 items-center gap-2">
            <span className="text-xs text-muted-foreground">InfraForge</span>
            <span className="text-xs text-muted-foreground">/</span>
            <span className="truncate text-sm font-medium">{title}</span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <StatusIndicator />
            <UserMenu />
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
