import { apiFetch } from "@/api/client";
import type { User } from "@/types/auth";
import type { AdminUserUpdateInput, UpdateProfileInput } from "@/types/user";

export function fetchUsers(): Promise<User[]> {
  return apiFetch<User[]>("/users");
}

export function updateProfile(input: UpdateProfileInput): Promise<User> {
  return apiFetch<User>("/users/me", {
    method: "PATCH",
    json: input,
  });
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/auth/change-password", {
    method: "POST",
    json: { current_password: currentPassword, new_password: newPassword },
  });
}

export function updateUser(
  userId: number,
  input: AdminUserUpdateInput,
): Promise<User> {
  return apiFetch<User>(`/users/${userId}`, {
    method: "PATCH",
    json: input,
  });
}
