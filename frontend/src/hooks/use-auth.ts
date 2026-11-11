import { useContext } from "react";

import { AuthContext, type AuthContextValue } from "@/store/auth-context";

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth harus dipakai di dalam AuthProvider.");
  }
  return context;
}
