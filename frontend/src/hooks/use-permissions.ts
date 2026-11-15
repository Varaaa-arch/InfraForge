import { useAuth } from "@/hooks/use-auth";
import type { UserRole } from "@/types/auth";

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
};

const ROLE_RANK: Record<UserRole, number> = {
  viewer: 1,
  developer: 2,
  admin: 3,
};

export interface Permissions {
  role: UserRole;
  label: string;
  isAdmin: boolean;
  canDeploy: boolean;
  canManageInfrastructure: boolean;
  canManageUsers: boolean;
  canManageSettings: boolean;
}

export function usePermissions(): Permissions {
  const { user } = useAuth();
  const role: UserRole = user?.role ?? "viewer";

  return {
    role,
    label: ROLE_LABELS[role],
    isAdmin: role === "admin",
    canDeploy: ROLE_RANK[role] >= ROLE_RANK.developer,
    canManageInfrastructure: role === "admin",
    canManageUsers: role === "admin",
    canManageSettings: role === "admin",
  };
}
