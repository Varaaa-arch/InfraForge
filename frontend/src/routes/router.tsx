import { createBrowserRouter } from "react-router-dom";

import { AppLayout } from "@/layouts/app-layout";
import { ProtectedRoute } from "@/routes/protected-route";

export const router = createBrowserRouter([
  {
    path: "/login",
    lazy: async () => {
      const { LoginPage } = await import("@/pages/login");
      return { Component: LoginPage };
    },
  },
  {
    path: "/register",
    lazy: async () => {
      const { RegisterPage } = await import("@/pages/register");
      return { Component: RegisterPage };
    },
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            index: true,
            lazy: async () => {
              const { DashboardPage } = await import("@/pages/dashboard");
              return { Component: DashboardPage };
            },
          },
          {
            path: "monitoring",
            lazy: async () => {
              const { MonitoringPage } = await import("@/pages/monitoring");
              return { Component: MonitoringPage };
            },
          },
          {
            path: "logs",
            lazy: async () => {
              const { LogsPage } = await import("@/pages/logs");
              return { Component: LogsPage };
            },
          },
          {
            path: "alerts",
            lazy: async () => {
              const { AlertsPage } = await import("@/pages/alerts");
              return { Component: AlertsPage };
            },
          },
          {
            path: "servers",
            lazy: async () => {
              const { ServersPage } = await import("@/pages/servers");
              return { Component: ServersPage };
            },
          },
          {
            path: "containers",
            lazy: async () => {
              const { ContainersPage } = await import("@/pages/containers");
              return { Component: ContainersPage };
            },
          },
        ],
      },
    ],
  },
  {
    path: "*",
    lazy: async () => {
      const { NotFoundPage } = await import("@/pages/not-found");
      return { Component: NotFoundPage };
    },
  },
]);
