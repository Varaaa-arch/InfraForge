import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-background p-6 text-center">
      <p className="text-6xl font-semibold tracking-tight text-muted-foreground/40">404</p>
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Halaman tidak ditemukan</h1>
        <p className="text-sm text-muted-foreground">
          Tautan yang Anda buka tidak tersedia atau sudah dipindahkan.
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to="/">
          <ArrowLeft className="size-4" />
          Kembali ke Dashboard
        </Link>
      </Button>
    </div>
  );
}
