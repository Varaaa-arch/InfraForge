"""
Loki Service — pencarian dan filtering log terpusat.

Berinteraksi dengan Loki HTTP API:
- ``GET /loki/api/v1/query_range`` → query LogQL (keyword, container, level).
- ``GET /loki/api/v1/label/container/values`` → daftar container yang punya log.

Label yang diharapkan dari pipeline Promtail:
- ``container``  : nama container Docker.
- ``level``      : error / warning / info / debug (hasil ekstraksi Promtail).
- ``stream``     : stdout / stderr.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger

from app.config import settings

# Filter level → ekspresi label LogQL.
# `error` dan `warning` memakai regex agar variasi penulisan (err, warn) ikut.
_LEVEL_EXPRESSIONS: dict[str, str] = {
    "error": 'level=~"error|err|critical|fatal"',
    "warning": 'level=~"warn|warning"',
    "info": 'level="info"',
    "debug": 'level="debug"',
}

# Nama container harus aman dimasukkan ke LogQL tanpa escaping rumit.
_CONTAINER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# Format rentang waktu: 30m, 1h, 7d, dst.
_LAST_PATTERN = re.compile(r"^(\d+)([smhd])$")
_UNIT_SECONDS: dict[str, int] = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Loki hanya menyimpan log sesuai retention (7 hari).
MAX_RANGE_SECONDS = 7 * 86400


@dataclass
class LogEntry:
    timestamp: str
    timestamp_ns: str
    line: str
    level: str | None = None
    container: str | None = None
    stream: str | None = None


@dataclass
class LogQueryResult:
    query: str
    entries: list[LogEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_logql_string(value: str) -> str:
    """Escape backslash dan double-quote agar aman di string LogQL."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_last(last: str) -> int:
    """Konversi rentang waktu (mis. ``1h``) menjadi detik."""
    match = _LAST_PATTERN.fullmatch(last)
    if match is None:
        raise ValueError(
            f"Format `last` tidak valid: {last!r}. Gunakan format seperti 30m, 1h, atau 7d."
        )
    seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
    if seconds <= 0 or seconds > MAX_RANGE_SECONDS:
        raise ValueError(
            "Rentang `last` harus antara 1 detik dan 7 hari (retention Loki)."
        )
    return seconds


def build_query(
    container: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
) -> str:
    """
    Bangun query LogQL dari filter yang diberikan.

    Contoh hasil:
        {container="infraforge-backend", level="info"} |= "GET /health"
    """
    matchers: list[str] = []

    if container:
        if _CONTAINER_PATTERN.fullmatch(container) is None:
            raise ValueError(f"Nama container tidak valid: {container!r}.")
        matchers.append(f'container="{_escape_logql_string(container)}"')
    else:
        matchers.append('container=~".+"')

    if level and level.lower() != "all":
        expression = _LEVEL_EXPRESSIONS.get(level.lower())
        if expression is None:
            allowed = ", ".join(sorted(_LEVEL_EXPRESSIONS))
            raise ValueError(
                f"Level tidak valid: {level!r}. Pilihan: all, {allowed}."
            )
        matchers.append(expression)

    query = "{" + ", ".join(matchers) + "}"

    if keyword:
        query += f' |= "{_escape_logql_string(keyword)}"'

    return query


def _request(path: str, params: dict[str, str]) -> dict[str, Any]:
    """GET ke Loki HTTP API dan kembalikan payload JSON."""
    url = f"{settings.LOKI_URL.rstrip('/')}{path}"
    try:
        response = httpx.get(url, params=params, timeout=settings.LOKI_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(f"Request ke Loki gagal ({url}): {exc}")
        raise RuntimeError(f"Gagal menghubungi Loki: {exc}") from exc
    return response.json()  # type: ignore[no-any-return]


def _ns_to_iso(timestamp_ns: str) -> str:
    """Konversi timestamp nanosecond (string) menjadi ISO 8601 UTC."""
    return datetime.fromtimestamp(
        int(timestamp_ns) / 1_000_000_000, tz=UTC
    ).isoformat()


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def query_logs(
    container: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
    last: str = "1h",
    limit: int = 200,
) -> LogQueryResult:
    """
    Ambil log dari Loki sesuai filter, diurutkan dari yang paling lama.

    Args:
        container: nama container (exact match).
        level: error / warning / info / debug / all.
        keyword: kata kunci pencarian (line filter).
        last: rentang waktu ke belakang (mis. 15m, 1h, 7d).
        limit: jumlah maksimum baris log.
    """
    query = build_query(container=container, level=level, keyword=keyword)

    end_ns = time.time_ns()
    start_ns = end_ns - _parse_last(last) * 1_000_000_000

    payload = _request(
        "/loki/api/v1/query_range",
        {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
            "direction": "backward",
        },
    )

    entries: list[LogEntry] = []
    for stream in payload.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        level_label = labels.get("level") or labels.get("detected_level")
        for timestamp_ns, line in stream.get("values", []):
            entries.append(
                LogEntry(
                    timestamp=_ns_to_iso(timestamp_ns),
                    timestamp_ns=timestamp_ns,
                    line=line,
                    level=level_label,
                    container=labels.get("container"),
                    stream=labels.get("stream"),
                )
            )

    # Loki mengembalikan terbaru dulu (direction=backward); UI butuh urutan lama → baru.
    entries.sort(key=lambda entry: int(entry.timestamp_ns))

    return LogQueryResult(query=query, entries=entries)


def list_containers() -> list[str]:
    """Daftar nama container yang memiliki stream log di Loki."""
    payload = _request("/loki/api/v1/label/container/values", {})
    containers = payload.get("data", [])
    return sorted(str(name) for name in containers)
