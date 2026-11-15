import type { UserRole } from "@/types/auth";

export interface UpdateProfileInput {
  username?: string;
  email?: string;
  full_name?: string;
}

export interface AdminUserUpdateInput {
  role?: UserRole;
  is_active?: boolean;
}
