import { execFileSync } from "node:child_process";
import { createHmac, randomUUID } from "node:crypto";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

interface SeedData {
  username: string;
  password: string;
  project_id: number;
  worker_application_id: number;
  live_deployment_id: number;
}

function composeExec(args: string[]): string {
  return execFileSync(
    "docker",
    ["compose", "exec", "-T", ...args],
    { cwd: repoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  ).trim();
}

function seed(): SeedData {
  const output = composeExec([
    "backend",
    "uv",
    "run",
    "--no-dev",
    "python",
    "scripts/seed_m7_e2e.py",
  ]);
  const lines = output.split("\n").filter(Boolean);
  return JSON.parse(lines[lines.length - 1] ?? "{}") as SeedData;
}

function githubSignature(body: string, secret: string): string {
  return `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;
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

async function postPush(
  request: APIRequestContext,
  token: string,
  branch: string,
): Promise<{ status: number; body: { data: { accepted: boolean } } }> {
  const payload = {
    ref: `refs/heads/${branch}`,
    repository: {
      full_name: "acme/infraforge-e2e",
      html_url: "https://github.com/acme/infraforge-e2e",
      clone_url: "https://github.com/acme/infraforge-e2e.git",
    },
    head_commit: {
      id: branch === "release" ? "b".repeat(40) : "a".repeat(40),
      message: "playwright",
    },
  };
  const raw = JSON.stringify(payload);
  const response = await request.post(`/api/v1/deploy/webhook/${token}`, {
    data: raw,
    headers: {
      "Content-Type": "application/json",
      "X-GitHub-Event": "push",
      "X-GitHub-Delivery": randomUUID(),
      "X-Hub-Signature-256": githubSignature(raw, token),
    },
  });
  return { status: response.status(), body: await response.json() };
}

test("Milestone 7: token, webhook, rollback, branch filter, dan live log", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  const data = seed();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await login(page, data.username, data.password);

  // Helper Git + pembuatan token dengan cakupan aplikasi.
  await page.goto(`/projects/${data.project_id}?tab=ci`);
  await expect(page.getByTestId("deploy-tokens-card")).toBeVisible();
  await page.getByTestId("webhook-deep-link").waitFor();
  await expect(page.getByTestId("webhook-deep-link")).toHaveAttribute(
    "href",
    "https://github.com/acme/infraforge-e2e/settings/hooks/new",
  );

  await page.getByTestId("deploy-token-name").fill("playwright-rotation");
  await page.getByTestId("deploy-token-application").click();
  await page.getByRole("option", { name: "worker", exact: true }).click();
  await page.getByTestId("deploy-token-create").click();

  const createdDialog = page.getByTestId("deploy-token-created-dialog");
  await expect(createdDialog).toBeVisible();
  const originalToken = (
    await createdDialog.getByTestId("deploy-token-plaintext").textContent()
  )?.trim();
  expect(originalToken).toBeTruthy();
  await createdDialog.getByRole("button", { name: "Selesai" }).click();

  const tokenRow = page
    .getByTestId("deploy-token-row")
    .filter({ hasText: "playwright-rotation" });
  await expect(tokenRow).toBeVisible();
  await tokenRow.getByTestId("deploy-token-rotate").click();
  await expect(page.getByTestId("deploy-token-rotate-dialog")).toBeVisible();
  await page.getByTestId("deploy-token-rotate-confirm").click();

  await expect(createdDialog).toBeVisible();
  const rotatedToken = (
    await createdDialog.getByTestId("deploy-token-plaintext").textContent()
  )?.trim();
  expect(rotatedToken).toBeTruthy();
  expect(rotatedToken).not.toBe(originalToken);
  await createdDialog.getByRole("button", { name: "Selesai" }).click();

  const oldTokenResponse = await request.post(
    `/api/v1/deploy/webhook/${originalToken}`,
    { data: {} },
  );
  expect(oldTokenResponse.status()).toBe(404);

  // Filter branch: worker hanya menerima branch release.
  await page.goto(`/projects/${data.project_id}?tab=summary`);
  const workerRow = page
    .getByTestId("project-app-row")
    .filter({ has: page.getByText("worker", { exact: true }) });
  await workerRow.getByTestId("application-branches-edit").click();
  const branchesDialog = page.getByTestId("application-branches-dialog");
  await expect(branchesDialog).toBeVisible();
  await branchesDialog.getByRole("button", { name: "Hapus branch main" }).click();
  await branchesDialog.getByTestId("application-branch-input").fill("release");
  await branchesDialog.getByTestId("application-branch-add").click();
  await branchesDialog.getByTestId("application-branches-save").click();
  await expect(branchesDialog).toBeHidden();
  await expect(workerRow.getByTestId("application-webhook-branches")).toContainText(
    "release",
  );

  const ignoredPush = await postPush(request, rotatedToken!, "main");
  expect(ignoredPush.status).toBe(202);
  expect(ignoredPush.body.data.accepted).toBe(false);

  const acceptedPush = await postPush(request, rotatedToken!, "release");
  expect(acceptedPush.status).toBe(202);
  expect(acceptedPush.body.data.accepted).toBe(true);

  // Riwayat menampilkan deployment dari webhook branch release.
  await page.goto(`/projects/${data.project_id}?tab=deployments`);
  const webhookRow = page
    .getByTestId("deployment-row")
    .filter({ has: page.getByText("worker", { exact: true }) })
    .filter({ hasText: "release" });
  await expect(webhookRow).toBeVisible();

  // Rollback versi stabil lama, bukan versi stabil terbaru.
  const rollbackRow = page
    .getByTestId("deployment-row")
    .filter({ has: page.getByText("v1.0.0", { exact: true }) });
  await expect(rollbackRow).toBeVisible();
  await rollbackRow.getByTestId("deployment-rollback-button").click();
  await expect(page.getByTestId("confirm-dialog")).toBeVisible();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByTestId("deployment-feedback")).toContainText(
    "dijadwalkan",
  );
  await expect(
    page
      .getByTestId("deployment-row")
      .filter({ has: page.getByTestId("deployment-rollback-badge") }),
  ).toBeVisible();

  // Live log: buka deployment yang masih deploying, tambah baris, lalu selesaikan.
  const liveRow = page
    .getByTestId("deployment-row")
    .filter({ has: page.getByText("log-worker", { exact: true }) });
  await liveRow.getByTestId("deployment-log-button").click();
  const logDialog = page.getByTestId("deployment-log-dialog");
  await expect(logDialog).toBeVisible();
  await expect(logDialog.getByTestId("deployment-log-status")).toHaveText("Live");
  await expect(logDialog.getByTestId("deployment-log-output")).toContainText(
    "Cloning repository...",
  );

  composeExec([
    "backend",
    "uv",
    "run",
    "--no-dev",
    "python",
    "scripts/seed_m7_e2e.py",
    "--append-log",
    "Build output line from Playwright",
  ]);
  await expect(logDialog.getByTestId("deployment-log-output")).toContainText(
    "Build output line from Playwright",
  );

  composeExec([
    "backend",
    "uv",
    "run",
    "--no-dev",
    "python",
    "scripts/seed_m7_e2e.py",
    "--finish-log",
    String(data.live_deployment_id),
  ]);
  await expect(logDialog.getByTestId("deployment-log-status")).toHaveText(
    "Selesai",
  );
  await expect(logDialog.getByTestId("deployment-log-output")).not.toContainText(
    "[INFRAFORGE:DONE]",
  );
  await logDialog.getByRole("button", { name: "Tutup" }).click();

  await liveRow.getByTestId("deployment-log-button").click();
  await expect(logDialog.getByTestId("deployment-log-output")).toContainText(
    "Build output line from Playwright",
  );
  await logDialog.getByRole("button", { name: "Tutup" }).click();

  // Audit webhook sukses/ditolak dan rotasi token tercatat.
  const accessToken = await apiAccessToken(
    request,
    data.username,
    data.password,
  );
  await expect
    .poll(async () => {
      const response = await request.get(
        "/api/audit-logs?action=DEPLOY_WEBHOOK&limit=50",
        { headers: { Authorization: `Bearer ${accessToken}` } },
      );
      const body = (await response.json()) as {
        data: { items: Array<{ details?: { outcome?: string } }> };
      };
      return body.data.items.map((item) => item.details?.outcome);
    })
    .toEqual(expect.arrayContaining(["no_match", "scheduled"]));

  const rotationAudit = await request.get(
    "/api/audit-logs?action=DEPLOY_TOKEN_ROTATE&limit=10",
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  const rotationBody = (await rotationAudit.json()) as {
    data: { total: number };
  };
  expect(rotationBody.data.total).toBeGreaterThan(0);

  expect(pageErrors).toEqual([]);
});
