interface JwtPayload {
  exp?: number;
}

export function isTokenExpiring(token: string, thresholdSeconds = 60): boolean {
  const parts = token.split(".");
  if (parts.length < 2) {
    return false;
  }

  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const payload = JSON.parse(atob(padded)) as JwtPayload;
    if (typeof payload.exp !== "number") {
      return false;
    }
    return payload.exp * 1000 - Date.now() <= thresholdSeconds * 1000;
  } catch {
    return false;
  }
}
