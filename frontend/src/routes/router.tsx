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
            path: "logs",
            lazy: async () => {
              const { LogsPage } = await import("@/pages/logs");
              return { Component: LogsPage };
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
