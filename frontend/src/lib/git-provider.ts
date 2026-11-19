import type { GitProvider } from "@/types/project";

const PROVIDER_LABEL: Record<GitProvider, string> = {
  github: "GitHub",
  gitlab: "GitLab",
  bitbucket: "Bitbucket",
};

export function providerLabel(provider: GitProvider | null | undefined): string {
  if (!provider) {
    return "Belum ditentukan";
  }
  return PROVIDER_LABEL[provider] ?? provider;
}

export function detectGitProvider(repositoryUrl: string | null): GitProvider | null {
  if (!repositoryUrl) {
    return null;
  }

  let host: string;
  try {
    host = new URL(repositoryUrl).hostname.toLowerCase();
  } catch {
    return null;
  }

  if (host === "github.com" || host.endsWith(".github.com") || host.includes("github")) {
    return "github";
  }
  if (host === "gitlab.com" || host.includes("gitlab")) {
    return "gitlab";
  }
  if (host.includes("bitbucket")) {
    return "bitbucket";
  }
  return null;
}

export function resolveGitProvider(
  provider: GitProvider | null,
  repositoryUrl: string | null,
): GitProvider | null {
  return provider ?? detectGitProvider(repositoryUrl);
}

function repositoryBaseUrl(repositoryUrl: string): string | null {
  try {
    const parsed = new URL(repositoryUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    const pathname = parsed.pathname
      .replace(/\/+$/, "")
      .replace(/\.git$/, "");
    if (!pathname) {
      return null;
    }
    return `${parsed.origin}${pathname}`;
  } catch {
    return null;
  }
}

export function buildWebhookSettingsUrl(
  provider: GitProvider | null,
  repositoryUrl: string | null,
): string | null {
  if (!repositoryUrl) {
    return null;
  }
  const resolved = resolveGitProvider(provider, repositoryUrl);
  const base = repositoryBaseUrl(repositoryUrl);
  if (!base || !resolved) {
    return null;
  }

  if (resolved === "github") {
    return `${base}/settings/hooks/new`;
  }
  if (resolved === "gitlab") {
    return `${base}/-/hooks`;
  }
  return null;
}
