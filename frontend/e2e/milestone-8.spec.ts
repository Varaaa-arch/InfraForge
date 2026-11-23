import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

interface SeedData {
  admin: { username: string; password: string };
  developer: { username: string; password: string };
  viewer: { username: string; password: string };
  image_scan_ids: {
    secure: number;
    unsafe: number;
    failed: number;
    viewer: number;
  };
  tls_domain_ids: {
    healthy: number;
    expiring: number;
    expired: number;
    invalid: number;
  };
  hosts: {
    healthy: string;
    expiring: string;
    expired: string;
    invalid: string;
  };
  trivy_available: boolean;
}

function composeExec(args: string[]): string {
  return execFileSync("docker", ["compose", "exec", "-T", ...args], {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function seed(): SeedData {
  const output = composeExec([
    "backend",
    "uv",
    "run",
    "--no-dev",
    "python",
    "scripts/seed_m8_e2e.py",
  ]);
  const lines = output.split("\n").filter(Boolean);
  return JSON.parse(lines[lines.length - 1] ?? "{}") as SeedData;
}

async function login(page: Page, username: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Masuk" }).click();
  await page.waitForURL((url) => url.pathname === "/");
}

async function apiAccessToken(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const response = await request.post("/api/auth/login", {
    form: { username, password },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as {
    data: { access_token: string };
  };
  return body.data.access_token;
}

async function auditTotal(
  request: APIRequestContext,
  token: string,
  action: string,
): Promise<number> {
  const response = await request.get(`/api/audit-logs?action=${action}&limit=50`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { data: { total: number } };
  return body.data.total;
}

test("Milestone 8: posture, CVE, TLS, audit, dan batasan role", async ({
  page,
  request,
}) => {
  test.setTimeout(300_000);
  const data = seed();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await login(page, data.admin.username, data.admin.password);

  // Dashboard menampilkan posture global.
  await expect(page.getByTestId("security-posture-card")).toBeVisible();
  await expect(page.getByTestId("security-posture-score")).toHaveText(/^\d+/);
  await expect(page.getByTestId("security-posture-level")).not.toBeEmpty();

  // Halaman keamanan: posture + temuan CVE dari seed.
  await page.goto("/security");
  const postureCard = page.getByTestId("security-posture-card");
  await expect(postureCard).toBeVisible();
  await expect(
    postureCard.getByTestId("security-posture-findings"),
  ).toContainText("CVE-2026-4242");

  const unsafeRow = page
    .getByTestId("image-scan-row")
    .filter({ hasText: "e2e/unsafe:1" });
  await expect(unsafeRow).toBeVisible();
  await unsafeRow.getByTestId("image-scan-detail").click();
  const scanDialog = page.getByTestId("image-scan-detail-dialog");
  await expect(scanDialog).toBeVisible();
  await expect(scanDialog).toContainText("CVE-2026-4242");
  await expect(scanDialog).toContainText("CVE-2026-4343");
  await scanDialog.getByRole("button", { name: "Tutup" }).click();

  // Status TLS expired tampil di tabel dan detail.
  await page.goto("/tls-domains");
  const expiredRow = page
    .getByTestId("tls-domain-row")
    .filter({ hasText: data.hosts.expired });
  await expect(expiredRow).toBeVisible();
  await expect(expiredRow.getByTestId("tls-status-badge")).toContainText(
    "Kedaluwarsa",
  );
  await expiredRow.getByTestId("tls-domain-detail").click();
  const tlsDialog = page.getByTestId("tls-domain-detail-dialog");
  await expect(tlsDialog).toBeVisible();
  await expect(tlsDialog).toContainText("Sertifikat sudah kedaluwarsa.");
  await tlsDialog.getByRole("button", { name: "Tutup" }).click();

  const adminToken = await apiAccessToken(
    request,
    data.admin.username,
    data.admin.password,
  );

  // Membaca posture juga tercatat di audit.
  await expect
    .poll(() => auditTotal(request, adminToken, "SECURITY_POSTURE_READ"))
    .toBeGreaterThan(0);

  // Scan nyata opsional: fallback aman bila Trivy tidak tersedia.
  if (data.trivy_available) {
    const developerToken = await apiAccessToken(
      request,
      data.developer.username,
      data.developer.password,
    );
    const scanResponse = await request.post("/api/image-scans", {
      data: { image_name: "alpine:3.20" },
      headers: { Authorization: `Bearer ${developerToken}` },
    });
    expect(scanResponse.status()).toBe(201);
    const scanBody = (await scanResponse.json()) as {
      data: { status: string; image_name: string };
    };
    expect(scanBody.data.image_name).toBe("alpine:3.20");
    expect(["completed", "failed"]).toContain(scanBody.data.status);
    await expect
      .poll(() => auditTotal(request, developerToken, "IMAGE_SCAN"))
      .toBeGreaterThan(0);
  }

  // Cek TLS memakai token admin dan harus teraudit.
  const checkResponse = await request.post(
    `/api/tls-domains/${data.tls_domain_ids.healthy}/check`,
    { headers: { Authorization: `Bearer ${adminToken}` } },
  );
  expect(checkResponse.status()).toBe(200);
  await expect
    .poll(() => auditTotal(request, adminToken, "TLS_DOMAIN_CHECK"))
    .toBeGreaterThan(0);

  // Viewer: baca posture/CVE/TLS, tetapi tidak boleh memicu mutasi.
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await login(page, data.viewer.username, data.viewer.password);
  await expect(page.getByTestId("security-posture-card")).toBeVisible();

  await page.goto("/security");
  await expect(page.getByTestId("security-posture-card")).toBeVisible();
  await expect(page.getByTestId("image-scan-input")).toBeDisabled();
  await expect(page.getByTestId("image-scan-submit")).toBeDisabled();
  const viewerRow = page
    .getByTestId("image-scan-row")
    .filter({ hasText: "e2e/viewer:1" });
  await expect(viewerRow).toBeVisible();
  await viewerRow.getByTestId("image-scan-detail").click();
  const viewerDialog = page.getByTestId("image-scan-detail-dialog");
  await expect(viewerDialog).toContainText("CVE-2026-4242");
  await expect(viewerDialog.getByTestId("image-scan-detail-rescan")).toHaveCount(0);
  await viewerDialog.getByRole("button", { name: "Tutup" }).click();

  await page.goto("/tls-domains");
  await expect(page.getByTestId("tls-domains-page")).toBeVisible();
  await expect(page.getByTestId("tls-domain-add")).toHaveCount(0);
  await expect(page.getByTestId("tls-domain-check")).toHaveCount(0);

  const viewerToken = await apiAccessToken(
    request,
    data.viewer.username,
    data.viewer.password,
  );
  const deniedScan = await request.post("/api/image-scans", {
    data: { image_name: "alpine:3.20" },
    headers: { Authorization: `Bearer ${viewerToken}` },
  });
  expect(deniedScan.status()).toBe(403);
  const deniedTls = await request.post("/api/tls-domains", {
    data: { host: "viewer.example.com", check_now: false },
    headers: { Authorization: `Bearer ${viewerToken}` },
  });
  expect(deniedTls.status()).toBe(403);

  expect(pageErrors).toEqual([]);
});
