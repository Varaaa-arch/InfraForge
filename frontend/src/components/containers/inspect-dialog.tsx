import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { fetchContainerInspect } from "@/api/containers";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type InspectTab = "summary" | "env" | "mounts" | "network";

const tabs: { value: InspectTab; label: string }[] = [
  { value: "summary", label: "Ringkasan" },
  { value: "env", label: "Env" },
  { value: "mounts", label: "Mounts" },
  { value: "network", label: "Network" },
];

interface InspectDialogProps {
  containerId: string | null;
  containerName?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

export function InspectDialog({
  containerId,
  containerName,
  open,
  onOpenChange,
}: InspectDialogProps) {
  const [tab, setTab] = useState<InspectTab>("summary");

  const inspectQuery = useQuery({
    queryKey: ["container-inspect", containerId],
    queryFn: () => fetchContainerInspect(containerId as string),
    enabled: open && containerId !== null,
    retry: 1,
  });

  const data = inspectQuery.data;
  const config = asRecord(asRecord(data).Config);
  const state = asRecord(asRecord(data).State);
  const networkSettings = asRecord(asRecord(data).NetworkSettings);

  const envEntries = asArray(config.Env).map((item) => {
    const raw = asString(item);
    const separator = raw.indexOf("=");
    return separator === -1
      ? { key: raw, value: "" }
      : { key: raw.slice(0, separator), value: raw.slice(separator + 1) };
  });

  const mounts = asArray(asRecord(data).Mounts).map((item) => {
    const mount = asRecord(item);
    return {
      type: asString(mount.Type),
      source: asString(mount.Source),
      destination: asString(mount.Destination),
      mode: asString(mount.RW) === "true" ? "rw" : "ro",
    };
  });

  const networks = Object.entries(asRecord(networkSettings.Networks)).map(
    ([name, value]) => {
      const network = asRecord(value);
      return {
        name,
        ip: asString(network.IPAddress),
        gateway: asString(network.Gateway),
        mac: asString(network.MacAddress),
      };
    },
  );

  const ports = Object.entries(asRecord(networkSettings.Ports)).flatMap(
    ([portKey, value]) => {
      const [portPart, protocol] = portKey.split("/");
      const bindings = asArray(value).map((binding) => {
        const entry = asRecord(binding);
        return `${asString(entry.HostIp) || "0.0.0.0"}:${asString(entry.HostPort)}`;
      });
      return [
        {
          port: `${portPart}/${protocol ?? "tcp"}`,
          bindings: bindings.length > 0 ? bindings.join(", ") : "exposed",
        },
      ];
    },
  );

  const errorMessage = inspectQuery.error
    ? inspectQuery.error instanceof ApiError
      ? inspectQuery.error.message
      : "Tidak dapat memuat detail container."
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl" data-testid="inspect-dialog">
        <DialogHeader>
          <DialogTitle>Inspect {containerName ?? "container"}</DialogTitle>
          <DialogDescription>
            Detail container setara output <code className="font-mono">docker inspect</code>.
          </DialogDescription>
        </DialogHeader>

        <div
          className="inline-flex items-center gap-1 self-start rounded-lg border bg-muted/40 p-1"
          role="tablist"
          aria-label="Bagian detail container"
        >
          {tabs.map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={tab === item.value}
              onClick={() => setTab(item.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm transition-colors",
                tab === item.value
                  ? "bg-background font-medium text-foreground shadow-sm ring-1 ring-foreground/10"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        {inspectQuery.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : errorMessage ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <TriangleAlert className="size-6 text-destructive" />
            <p className="text-sm text-destructive">{errorMessage}</p>
          </div>
        ) : (
          <div className="max-h-[55vh] overflow-y-auto">
            {tab === "summary" ? (
              <pre
                className="rounded-lg border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
                data-testid="inspect-json"
              >
                {JSON.stringify(data, null, 2)}
              </pre>
            ) : null}

            {tab === "env" ? (
              <div className="overflow-x-auto">
                <Table data-testid="inspect-env">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Key</TableHead>
                      <TableHead>Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {envEntries.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-muted-foreground">
                          Container tidak memiliki environment variable.
                        </TableCell>
                      </TableRow>
                    ) : (
                      envEntries.map((entry) => (
                        <TableRow key={entry.key}>
                          <TableCell className="font-mono text-xs whitespace-nowrap">
                            {entry.key}
                          </TableCell>
                          <TableCell className="font-mono text-xs break-all">
                            {entry.value}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            ) : null}

            {tab === "mounts" ? (
              <div className="overflow-x-auto">
                <Table data-testid="inspect-mounts">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tipe</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Destination</TableHead>
                      <TableHead>Mode</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {mounts.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-muted-foreground">
                          Container tidak memiliki mount.
                        </TableCell>
                      </TableRow>
                    ) : (
                      mounts.map((mount) => (
                        <TableRow key={`${mount.type}-${mount.destination}`}>
                          <TableCell className="text-xs">{mount.type}</TableCell>
                          <TableCell className="font-mono text-xs break-all">
                            {mount.source || "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs break-all">
                            {mount.destination}
                          </TableCell>
                          <TableCell className="text-xs">{mount.mode}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            ) : null}

            {tab === "network" ? (
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <Table data-testid="inspect-network">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Network</TableHead>
                        <TableHead>IP Address</TableHead>
                        <TableHead>Gateway</TableHead>
                        <TableHead>MAC</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {networks.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="text-muted-foreground">
                            Container tidak terhubung ke network.
                          </TableCell>
                        </TableRow>
                      ) : (
                        networks.map((network) => (
                          <TableRow key={network.name}>
                            <TableCell className="text-xs">{network.name}</TableCell>
                            <TableCell className="font-mono text-xs">
                              {network.ip || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {network.gateway || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {network.mac || "—"}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>

                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">Port mapping</p>
                  <div className="flex flex-wrap gap-1">
                    {ports.length === 0 ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : (
                      ports.map((port) => (
                        <Badge key={port.port} variant="outline" className="font-mono text-[10px]">
                          {port.port} → {port.bindings}
                        </Badge>
                      ))
                    )}
                  </div>
                </div>
              </div>
            ) : null}

            {tab === "summary" ? (
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>
                  Status:{" "}
                  <span className="text-foreground">{asString(state.Status) || "—"}</span>
                </span>
                <span>
                  Image:{" "}
                  <span className="text-foreground">
                    {asString(asRecord(config.Image)) || "—"}
                  </span>
                </span>
                <span>
                  Restart:{" "}
                  <span className="text-foreground">
                    {asString(asRecord(data).RestartCount) || "0"}
                  </span>
                </span>
              </div>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
