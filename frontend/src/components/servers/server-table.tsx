import { Activity, Pencil, PlugZap, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Server, ServerExporterStatus, ServerStatus } from "@/types/server";

const exporterStyles: Record<ServerExporterStatus, { label: string; className: string }> = {
  up: {
    label: "Aktif",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  down: {
    label: "Down",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
  not_configured: {
    label: "Belum diisi",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  unknown: {
    label: "Tidak diketahui",
    className: "border-slate-500/30 bg-slate-500/10 text-slate-600 dark:text-slate-300",
  },
};

const sshStyles: Record<ServerStatus, { label: string; className: string }> = {
  active: {
    label: "Active",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  inactive: {
    label: "Inactive",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  error: {
    label: "Error",
    className: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  },
};

interface ServerTableProps {
  servers: Server[];
  busyServerId?: number | null;
  onEdit: (server: Server) => void;
  onTest: (server: Server) => void;
  onDelete: (server: Server) => void;
}

export function ServerTable({
  servers,
  busyServerId = null,
  onEdit,
  onTest,
  onDelete,
}: ServerTableProps) {
  return (
    <div className="overflow-x-auto">
      <Table data-testid="server-table">
        <TableHeader>
          <TableRow>
            <TableHead>Nama</TableHead>
            <TableHead>Host</TableHead>
            <TableHead>User</TableHead>
            <TableHead>Exporter</TableHead>
            <TableHead>Status Prometheus</TableHead>
            <TableHead>Status SSH</TableHead>
            <TableHead className="text-right">Aksi</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {servers.map((server) => {
            const exporter = exporterStyles[server.exporter_status ?? "unknown"];
            const ssh = sshStyles[server.status];
            const busy = busyServerId === server.id;

            return (
              <TableRow key={server.id} data-testid="server-row">
                <TableCell className="font-medium">{server.name}</TableCell>
                <TableCell className="font-mono text-xs">
                  {server.host}:{server.port}
                </TableCell>
                <TableCell className="text-xs">{server.username}</TableCell>
                <TableCell className="font-mono text-xs">
                  {server.exporter_instance ?? "—"}
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={cn("gap-1.5", exporter.className)}
                    data-testid="server-exporter-status"
                  >
                    <span className="size-1.5 rounded-full bg-current" />
                    {exporter.label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn("gap-1.5", ssh.className)}>
                    <span className="size-1.5 rounded-full bg-current" />
                    {ssh.label}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button
                      asChild
                      variant="ghost"
                      size="icon-sm"
                      title="Buka grafik monitoring"
                      aria-label={`Grafik ${server.name}`}
                    >
                      <Link to={`/monitoring?server=${server.id}`}>
                        <Activity />
                      </Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Tes koneksi SSH"
                      aria-label={`Tes koneksi ${server.name}`}
                      disabled={busy}
                      onClick={() => onTest(server)}
                    >
                      <PlugZap />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Ubah server"
                      aria-label={`Ubah ${server.name}`}
                      onClick={() => onEdit(server)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive"
                      title="Hapus server"
                      aria-label={`Hapus ${server.name}`}
                      onClick={() => onDelete(server)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
