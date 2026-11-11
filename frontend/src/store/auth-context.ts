import { createContext } from "react";

import type { AuthStatus, User } from "@/types/auth";

export interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
