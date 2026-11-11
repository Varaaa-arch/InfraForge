import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck } from "lucide-react";

import { apiFetch } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface HealthResponse {
  status: string;
}

export function StatusIndicator() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health"),
    refetchInterval: 30_000,
    retry: 1,
  });

  if (healthQuery.isLoading) {
    return <Skeleton className="h-6 w-24 rounded-full" />;
  }

  if (healthQuery.isError) {
    return (
      <Badge variant="destructive" className="gap-1.5">
        <CircleAlert className="size-3" />
        <span className="hidden sm:inline">API offline</span>
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
      <CircleCheck className="size-3" />
      <span className="hidden sm:inline">API online</span>
    </Badge>
  );
}
