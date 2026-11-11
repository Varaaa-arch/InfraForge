import { Loader2 } from "lucide-react";

export function FullScreenLoader({ label = "Memuat…" }: { label?: string }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-background">
      <div className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
