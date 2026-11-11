"""
WebSocket handler untuk tail log terpusat dari Loki.

Endpoint:
    GET /ws/logs?token=<access_token>&container=<nama>&q=<keyword>&level=<level>

Protokol:
    - Klien koneksi via WebSocket (ws:// atau wss://).
    - Autentikasi via query parameter `token` (JWT access token).
    - Server meneruskan setiap baris log baru dari Loki HTTP API
      (`/loki/api/v1/tail`) sebagai pesan JSON:

        {
          "timestamp": "2026-11-11T12:35:06.758775+00:00",
          "timestamp_ns": "1762864506758775000",
          "line": "INFO: ...",
          "level": "info",
          "container": "infraforge-backend",
          "stream": "stdout"
        }

    - Jika terjadi error (token invalid, query invalid, Loki tidak bisa
      dihubungi), server mengirim `{"error": "..."}` lalu menutup koneksi.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import WebSocketException

from app.config import settings
from app.core.security import decode_token
from app.database.session import get_db
from app.services import auth_service, loki_service

router_ws_logs = APIRouter(tags=["websocket"])


def _get_db_session() -> Session:
    """Buat session DB baru untuk konteks non-Depends (WebSocket)."""
    return next(get_db())


def _authenticate(token: str) -> int | None:
    """Validasi JWT dan pastikan user aktif. Return user_id atau None."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        return None
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        return None

    db = _get_db_session()
    try:
        user = auth_service.get_user_by_id(db, user_id)
        if user is None or not user.is_active:
            return None
        return user_id
    finally:
        db.close()


def parse_tail_payload(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    """
    Ubah payload tail Loki menjadi daftar entry siap kirim ke klien.

    Format payload Loki:
        {"streams": [{"stream": {...labels}, "values": [[ts_ns, line], ...]}]}
    """
    entries: list[dict[str, str | None]] = []

    for stream_obj in payload.get("streams") or []:
        labels = stream_obj.get("stream") or {}
        level = labels.get("level") or labels.get("detected_level")

        for value in stream_obj.get("values") or []:
            if len(value) < 2:
                continue
            timestamp_ns, line = value[0], value[1]
            entries.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        int(timestamp_ns) / 1_000_000_000, tz=UTC
                    ).isoformat(),
                    "timestamp_ns": str(timestamp_ns),
                    "line": line,
                    "level": level,
                    "container": labels.get("container"),
                    "stream": labels.get("stream"),
                }
            )

    entries.sort(key=lambda entry: int(entry["timestamp_ns"] or 0))
    return entries


def _tail_url(query: str) -> str:
    """Bangun URL WebSocket tail Loki dari LOKI_URL (http/https → ws/wss)."""
    base = settings.LOKI_URL.rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://") :]
    else:
        ws_base = base
    # Mulai dari ~1 detik lalu agar log yang masuk bersamaan dengan koneksi
    # tetap tertangkap, tanpa memutar ulang seluruh backlog Loki.
    start_ns = time.time_ns() - 1_000_000_000
    params = urlencode(
        {"query": query, "limit": "100", "start": str(start_ns)}
    )
    return f"{ws_base}/loki/api/v1/tail?{params}"


async def _stream_loki(websocket: WebSocket, query: str) -> None:
    """Stream baris log baru dari Loki tail API (WebSocket) ke WebSocket klien."""
    url = _tail_url(query)

    try:
        async with ws_connect(url, open_timeout=settings.LOKI_TIMEOUT) as loki_ws:
            async for raw_line in loki_ws:
                text = (
                    raw_line.decode("utf-8", errors="replace")
                    if isinstance(raw_line, bytes)
                    else raw_line
                )
                if not text.strip():
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning(f"Pesan tail Loki bukan JSON valid: {text[:120]}")
                    continue

                for entry in parse_tail_payload(payload):
                    await websocket.send_json(entry)
    except WebSocketException as exc:
        raise RuntimeError(f"Koneksi tail Loki gagal: {exc}") from exc


@router_ws_logs.websocket("/ws/logs")
async def logs_ws(
    websocket: WebSocket,
    token: str = Query(description="JWT access token untuk autentikasi WebSocket"),
    container: str | None = Query(
        default=None, description="Filter nama container (exact match)"
    ),
    q: str | None = Query(default=None, description="Keyword pencarian di isi log"),
    level: str | None = Query(
        default=None, description="Filter level: error, warning, info, debug, all"
    ),
) -> None:
    """
    **WebSocket** — Stream log container secara real-time (tail Loki).

    **Protokol**: `ws://host/ws/logs?token=<jwt>&container=<nama>&q=<keyword>&level=<level>`

    **Alur**:
    1. Autentikasi token JWT via query param `token`.
    2. Validasi filter dan bangun query LogQL.
    3. Stream log baru dari Loki dan kirim per entry sebagai JSON.

    **Catatan**: Endpoint ini menggunakan protokol WebSocket (`ws://` atau
    `wss://`) dan tidak dapat diuji langsung dari Swagger UI.
    """
    await websocket.accept()

    user_id = _authenticate(token)
    if user_id is None:
        await websocket.send_json({"error": "Token tidak valid."})
        await websocket.close(code=4001)
        return

    try:
        query = loki_service.build_query(
            container=container, level=level, keyword=q
        )
    except ValueError as exc:
        await websocket.send_json({"error": str(exc)})
        await websocket.close(code=4002)
        return

    logger.info(f"WebSocket log stream terhubung: user #{user_id} query={query}")

    try:
        await _stream_loki(websocket, query)
    except WebSocketDisconnect:
        logger.info(f"WebSocket log stream terputus: user #{user_id}")
        return
    except (RuntimeError, OSError, WebSocketException) as exc:
        logger.warning(f"WebSocket log stream gagal: {exc}")
        try:
            await websocket.send_json({"error": f"Gagal streaming log: {exc}"})
        except (WebSocketDisconnect, RuntimeError, OSError):
            return

    await websocket.close()
