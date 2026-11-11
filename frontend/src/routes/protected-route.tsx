import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullScreenLoader } from "@/components/full-screen-loader";
import { useAuth } from "@/hooks/use-auth";

export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <FullScreenLoader label="Memuat sesi…" />;
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
