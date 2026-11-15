import { ArrowRight, BellRing } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function NotificationsTab() {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <BellRing className="size-4" />
          Notifikasi
        </CardTitle>
        <CardDescription>
          Tujuan notifikasi alert (Discord/Telegram) dikelola di halaman Alerts
          bersama channel lainnya.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Tambah, uji, aktifkan, atau hapus channel notifikasi dari tab
          <span className="font-medium text-foreground"> Channel</span> pada halaman
          Alerts. Setiap alert firing/resolved akan dikirim ke channel yang aktif.
        </p>
        <Button asChild variant="outline" size="sm">
          <Link to="/alerts">
            Buka manajemen channel
            <ArrowRight className="size-3.5" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
