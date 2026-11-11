import { RouterProvider } from "react-router-dom";

import { router } from "@/routes/router";
import { AuthProvider } from "@/store/auth-provider";

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
