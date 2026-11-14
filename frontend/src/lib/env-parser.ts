/**
 * Parser isi file `.env` untuk Bulk Import.
 *
 * Aturan parsing:
 * - Baris kosong dan baris komentar (`#`) diabaikan.
 * - Prefix `export ` dibuang.
 * - Pemisah key/value adalah `=` pertama.
 * - Value diktrim; tanda kutip pembungkus (`"..."` / `'...'`) dilepas.
 * - Key divalidasi dengan pola POSIX (`^[A-Za-z_][A-Za-z0-9_]*$`) lalu
 *   dinormalisasi ke uppercase — sama seperti validasi backend.
 * - Key duplikat di dalam satu file dilewati (baris pertama menang).
 *
 * Fungsi ini murni (tanpa side effect) agar mudah diuji.
 */

export interface ParsedEnvEntry {
  key: string;
  value: string;
}

export interface SkippedEnvLine {
  lineNumber: number;
  content: string;
  reason: string;
}

export interface ParsedDotEnv {
  entries: ParsedEnvEntry[];
  skipped: SkippedEnvLine[];
}

const ENV_KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

function stripQuotes(value: string): string {
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1);
    }
  }
  return value;
}

export function parseDotEnv(text: string): ParsedDotEnv {
  const entries: ParsedEnvEntry[] = [];
  const skipped: SkippedEnvLine[] = [];
  const seen = new Set<string>();

  const lines = text.split(/\r?\n/);

  lines.forEach((rawLine, index) => {
    const lineNumber = index + 1;
    const trimmed = rawLine.trim();

    if (!trimmed) {
      return;
    }
    if (trimmed.startsWith("#")) {
      return;
    }

    const withoutExport = trimmed.startsWith("export ")
      ? trimmed.slice("export ".length).trim()
      : trimmed;

    const separator = withoutExport.indexOf("=");
    if (separator === -1) {
      skipped.push({
        lineNumber,
        content: trimmed,
        reason: "Format harus KEY=VALUE",
      });
      return;
    }

    const rawKey = withoutExport.slice(0, separator).trim();
    const rawValue = withoutExport.slice(separator + 1).trim();

    if (!rawKey) {
      skipped.push({
        lineNumber,
        content: trimmed,
        reason: "Key kosong",
      });
      return;
    }
    if (!ENV_KEY_PATTERN.test(rawKey)) {
      skipped.push({
        lineNumber,
        content: trimmed,
        reason: "Key tidak valid (hanya huruf, angka, dan underscore)",
      });
      return;
    }

    const key = rawKey.toUpperCase();
    if (seen.has(key)) {
      skipped.push({
        lineNumber,
        content: trimmed,
        reason: "Key duplikat di dalam file",
      });
      return;
    }

    const value = stripQuotes(rawValue);
    if (!value) {
      skipped.push({
        lineNumber,
        content: trimmed,
        reason: "Value kosong",
      });
      return;
    }

    seen.add(key);
    entries.push({ key, value });
  });

  return { entries, skipped };
}
