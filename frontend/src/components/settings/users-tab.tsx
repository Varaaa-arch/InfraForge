import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { fetchUsers, updateUser } from "@/api/users";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/hooks/use-auth";
import type { User, UserRole } from "@/types/auth";

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
};

const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  admin: "Akses penuh termasuk server, pengguna, dan channel notifikasi.",
  developer: "Deploy dan kelola project, env var, aplikasi, serta container.",
  viewer: "Hanya baca: monitoring, log, dan riwayat.",
};

const dateFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
});

export function UsersTab() {
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuth();
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  const mutation = useMutation({
    mutationFn: ({
      user,
      role,
      isActive,
    }: {
      user: User;
      role?: UserRole;
      isActive?: boolean;
    }) =>
      updateUser(user.id, {
        ...(role !== undefined ? { role } : {}),
        ...(isActive !== undefined ? { is_active: isActive } : {}),
      }),
    onSuccess: (updated) => {
      setFeedback({
        type: "success",
        message:
          updated.role !== undefined && updated.is_active
            ? `${updated.username} diperbarui (${ROLE_LABELS[updated.role]}).`
            : `${updated.username} diperbarui.`,
      });
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) =>
      setFeedback({
        type: "error",
        message:
          error instanceof ApiError ? error.message : "Gagal memperbarui pengguna.",
      }),
  });

  const changingId = mutation.isPending ? mutation.variables?.user.id : undefined;
  const users = usersQuery.data ?? [];

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <ShieldCheck className="size-4" />
          Pengguna
        </CardTitle>
        <CardDescription>
          Ubah peran dan status akun. Akun sendiri tidak dapat diubah, dan admin
          terakhir tidak dapat diturunkan.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {feedback ? (
          <div
            data-testid="users-feedback"
            className={
              feedback.type === "success"
                ? "flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400"
                : "flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            }
          >
            {feedback.type === "success" ? (
              <CheckCircle2 className="size-4 shrink-0" />
            ) : (
              <XCircle className="size-4 shrink-0" />
            )}
            {feedback.message}
          </div>
        ) : null}

        {usersQuery.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead className="w-40">Peran</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Bergabung</TableHead>
                  <TableHead className="text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => {
                  const isSelf = user.id === currentUser?.id;
                  const busy = changingId === user.id;
                  return (
                    <TableRow key={user.id} data-testid="user-row">
                      <TableCell className="font-medium">
                        {user.username}
                        {isSelf ? (
                          <span className="ml-2 text-xs text-muted-foreground">
                            (Anda)
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {user.email}
                      </TableCell>
                      <TableCell>
                        <Select
                          value={user.role}
                          disabled={isSelf || busy}
                          onValueChange={(value) =>
                            mutation.mutate({ user, role: value as UserRole })
                          }
                        >
                          <SelectTrigger
                            className="h-8 w-36"
                            data-testid={`user-role-${user.id}`}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {(Object.keys(ROLE_LABELS) as UserRole[]).map((role) => (
                              <SelectItem key={role} value={role}>
                                {ROLE_LABELS[role]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.is_active ? "default" : "secondary"}>
                          {user.is_active ? "Aktif" : "Nonaktif"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {dateFormatter.format(new Date(user.created_at))}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant={user.is_active ? "outline" : "default"}
                          size="sm"
                          data-testid={`user-toggle-${user.id}`}
                          disabled={isSelf || busy}
                          onClick={() =>
                            mutation.mutate({
                              user,
                              isActive: !user.is_active,
                            })
                          }
                        >
                          {busy ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : null}
                          {user.is_active ? "Nonaktifkan" : "Aktifkan"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}

        <div className="space-y-1 text-xs text-muted-foreground">
          {(Object.keys(ROLE_LABELS) as UserRole[]).map((role) => (
            <p key={role}>
              <span className="font-medium text-foreground">
                {ROLE_LABELS[role]}:
              </span>{" "}
              {ROLE_DESCRIPTIONS[role]}
            </p>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
