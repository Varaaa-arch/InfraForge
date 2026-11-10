"""
Sanitasi environment variable key dan value sebelum disimpan ke DB atau
ditulis ke file .env.

Ancaman yang dimitigasi:
  1. Newline injection (\n, \r) — bisa merusak struktur .env file dan
     menyisipkan key/value palsu di baris berikutnya.
  2. Null byte injection (\x00) — bisa truncate string di level OS/C library.
  3. Karakter kontrol lain (\x01-\x1f kecuali TAB) — tidak valid dalam value
     .env dan bisa menyebabkan behavior tidak terduga di shell.

Strategi sanitasi:
  - Input layer (schema): REJECT value yang mengandung newline/null byte
    (raise ValueError agar user sadar ada masalah).
  - Output layer (_write_env_file): SANITASI defensif — strip karakter
    berbahaya dan quote value agar aman ditulis ke file .env.

Format .env yang dihasilkan mengikuti konvensi dotenv:
  KEY="value with spaces"   # nilai di-double-quote
  KEY=simplevalue           # nilai tanpa spasi tidak perlu quote
"""

from __future__ import annotations

import re
import string

# Karakter yang DILARANG dalam value .env (input layer — trigger reject)
# \n, \r, \x00 adalah yang paling berbahaya
_FORBIDDEN_IN_VALUE: re.Pattern[str] = re.compile(r"[\n\r\x00]")

# Karakter kontrol yang dibersihkan saat output layer
# (semua ASCII control chars kecuali TAB \x09 yang masih lazim di value)
_CONTROL_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x08\x0a-\x0d\x0e-\x1f\x7f]")

# Karakter yang memerlukan quoting dalam .env value
_NEEDS_QUOTING: re.Pattern[str] = re.compile(r'[\s"\'\\#$`!]')


def sanitize_env_value_input(value: str) -> str:
    """
    Sanitasi value env var di input layer (schema validation).

    Perilaku:
      - Strip leading/trailing whitespace.
      - REJECT jika mengandung newline (\\n, \\r) atau null byte (\\x00).
        Karakter ini tidak valid dalam .env value dan bisa dipakai
        untuk menyisipkan baris palsu ke file .env.

    Args:
        value: Nilai plaintext env var dari user input.

    Returns:
        Value yang sudah di-strip whitespace.

    Raises:
        ValueError: Jika value mengandung newline atau null byte.
    """
    stripped = value.strip()

    match = _FORBIDDEN_IN_VALUE.search(stripped)
    if match:
        char = repr(match.group(0))
        raise ValueError(
            f"Value env var mengandung karakter yang tidak diizinkan: {char}. "
            f"Newline (\\n, \\r) dan null byte (\\x00) tidak diperbolehkan."
        )

    return stripped


def sanitize_env_key_input(key: str) -> str:
    """
    Sanitasi key env var di input layer.

    Perilaku:
      - Strip whitespace.
      - REJECT jika mengandung karakter selain huruf, angka, underscore,
        atau diawali angka (sudah ditangani oleh regex di schema, tapi
        fungsi ini bisa dipakai standalone).

    Args:
        key: Nama key env var.

    Returns:
        Key yang sudah di-strip dan di-uppercase.

    Raises:
        ValueError: Jika key mengandung karakter tidak valid.
    """
    stripped = key.strip().upper()

    if not stripped:
        raise ValueError("Key env var tidak boleh kosong.")

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stripped):
        raise ValueError(
            f"Key env var '{stripped}' tidak valid. "
            "Hanya huruf, angka, dan underscore yang diizinkan, "
            "serta tidak boleh diawali angka."
        )

    return stripped


def sanitize_env_value_output(value: str) -> str:
    """
    Sanitasi value env var di output layer (saat menulis ke file .env).

    Defense-in-depth — berasumsi value sudah lolos input validation tapi
    tambahkan lapisan keamanan ekstra untuk mencegah corruption .env file:

      1. Strip karakter kontrol berbahaya (\\x00-\\x1f kecuali TAB).
      2. Double-quote value jika mengandung spasi, tanda kutip, $, `, #, dll.
         Kutipan ganda mencegah shell melakukan word splitting dan expansion
         saat .env di-source oleh shell script.
      3. Escape double-quote dan backslash di dalam value.

    Args:
        value: Nilai plaintext yang akan ditulis ke .env.

    Returns:
        Value yang sudah di-sanitasi dan siap ditulis ke baris .env.
    """
    # 1. Strip karakter kontrol berbahaya
    cleaned = _CONTROL_CHARS.sub("", value)

    # 2. Jika value kosong setelah sanitasi, kembalikan string kosong
    if not cleaned:
        return '""'

    # 3. Cek apakah perlu quoting
    if _NEEDS_QUOTING.search(cleaned):
        # Escape backslash dan double-quote di dalam value
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    return cleaned


def build_env_file_line(key: str, value: str) -> str:
    """
    Bangun satu baris .env yang sudah disanitasi.

    Format: KEY=value atau KEY="value with spaces"

    Args:
        key:   Key env var (akan di-sanitasi).
        value: Value plaintext (akan di-sanitasi untuk output).

    Returns:
        Satu baris .env yang aman, diakhiri \\n.
    """
    safe_key = sanitize_env_key_input(key)
    safe_value = sanitize_env_value_output(value)
    return f"{safe_key}={safe_value}\n"
