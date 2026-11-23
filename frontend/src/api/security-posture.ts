import { apiFetch } from "@/api/client";
import type { SecurityPostureSummary } from "@/types/security-posture";

export function fetchSecurityPosture(): Promise<SecurityPostureSummary> {
  return apiFetch<SecurityPostureSummary>("/security/posture");
}
