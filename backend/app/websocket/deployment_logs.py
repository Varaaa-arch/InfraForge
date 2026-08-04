"""
WebSocket handler untuk Live Logs Deployment (Task 3.9).

Endpoint:
    GET /ws/deployments/{deployment_id}/logs?token=<access_token>

Protokol:
    - Klien koneksi via WebSocket (ws:// atau wss://).
    - Autentikasi via query parameter `token` (JWT access token).
    - Server stream log baris per baris dari file log deployment secara
      real-time hingga deployment selesai (status success / failed).
    - Setelah selesai, server mengirim pesan sentinel khusus
      `[INFRAFORGE:DONE]` lalu menutup koneksi.

Flow internal:
    1. Validasi token JWT dari query param.
    2. Ambil deployment dari DB; pastikan deployment milik user yang login.
    3. Jika log_path belum tersedia (deployment masih pending / baru dibuat),
       tunggu hingga log_path terisi (polling singkat).
    4. Buka file log dan stream baris baru menggunakan tail-like loop:
       - Baca baris baru → kirim ke WebSocket.
       - Jika tidak ada baris baru, cek status deployment:
         * Jika masih deploying → `asyncio.sleep(POLL_INTERVAL)` lalu coba lagi.
         * Jika sudah terminal (success/failed) → kirim sentinel lalu close.
    5. Tangani WebSocketDisconnect dengan bersih.

Catatan dokumentasi (WebSocket — tidak muncul di Swagger REST):
    WebSocket tidak didukung secara native di Swagger UI untuk di-test
    langsung, namun endpoint ini terdokumentasi di docstring ini.
    Gunakan tool seperti `websocat` atau browser WebSocket API untuk uji
    manual:
        ws://localhost:8000/ws/deployments/42/logs?token=<jwt>
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.database.session import get_db
from app.models.deployment import DeploymentStatus
from app.repositories import deployment_repository
from app.services import auth_service

# Polling interval saat menunggu baris log baru (detik)
POLL_INTERVAL: float = 0.5

# Batas waktu tunggu log_path tersedia setelah koneksi (detik)
LOG_PATH_WAIT_TIMEOUT: float = 30.0

# Pesan sentinel yang dikirim ke klien saat deployment selesai
DONE_SENTINEL = "[INFRAFORGE:DONE]"

# Status yang dianggap terminal (tidak akan ada log baru setelahnya)
_TERMINAL_STATUSES = frozenset({DeploymentStatus.success, DeploymentStatus.failed})

router = APIRouter(
    prefix="/ws",
    tags=["websocket"],
)


def _get_db_session() -> Session:
    """Buat session DB baru untuk konteks non-Depends (WebSocket)."""
    return next(get_db())


async def _wait_for_log_path(
    deployment_id: int,
    db: Session,
    timeout: float = LOG_PATH_WAIT_TIMEOUT,
) -> str | None:
    """
    Polling sampai log_path tersedia di DB atau timeout tercapai.

    Returns:
        log_path string jika tersedia, None jika timeout.
    """
    elapsed = 0.0
    while elapsed < timeout:
        dep = deployment_repository.get_by_id(db, deployment_id)
        if dep is not None and dep.log_path:
            return dep.log_path
        # Jika deployment sudah terminal tapi log_path masih None → tidak akan ada log
        if dep is not None and dep.status in _TERMINAL_STATUSES:
            return dep.log_path  # bisa None jika deployment selesai tanpa log
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return None


async def _stream_log_file(
    websocket: WebSocket,
    log_path: str,
    deployment_id: int,
    db: Session,
) -> None:
    """
    Stream baris baru dari file log ke WebSocket menggunakan tail-like loop.

    Loop berhenti saat:
    - Deployment mencapai status terminal (success/failed) DAN tidak ada baris baru.
    - WebSocket terputus (WebSocketDisconnect).
    """
    path = Path(log_path)
    file_offset = 0  # byte offset terakhir yang sudah dibaca

    try:
        while True:
            # Baca baris baru dari posisi terakhir
            new_lines: list[str] = []
            if path.exists():
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(file_offset)
                    chunk = f.read()
                    if chunk:
                        file_offset += len(chunk.encode("utf-8"))
                        new_lines = chunk.splitlines(keepends=True)

            # Kirim setiap baris baru ke klien
            for line in new_lines:
                await websocket.send_text(line.rstrip("\n"))

            # Cek status deployment dari DB
            dep = deployment_repository.get_by_id(db, deployment_id)
            if dep is not None and dep.status in _TERMINAL_STATUSES:
                # Satu putaran ekstra untuk memastikan tidak ada sisa log
                if not new_lines:
                    await websocket.send_text(DONE_SENTINEL)
                    break

            await asyncio.sleep(POLL_INTERVAL)

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket klien memutus koneksi untuk deployment #{deployment_id}"
        )


router_ws = APIRouter(tags=["websocket"])


@router_ws.websocket("/ws/deployments/{deployment_id}/logs")
async def deployment_logs_ws(
    websocket: WebSocket,
    deployment_id: int,
    token: str = Query(description="JWT access token untuk autentikasi WebSocket"),
) -> None:
    """
    **WebSocket** — Stream log deployment secara real-time.

    **Protokol**: `ws://host/ws/deployments/{deployment_id}/logs?token=<jwt>`

    **Alur**:
    1. Autentikasi token JWT via query param `token`.
    2. Validasi deployment milik user yang login.
    3. Stream setiap baris baru dari file log deployment.
    4. Kirim `[INFRAFORGE:DONE]` saat deployment selesai, lalu tutup koneksi.

    **Catatan**: Endpoint ini menggunakan protokol WebSocket (`ws://` atau
    `wss://`) dan tidak dapat diuji langsung dari Swagger UI. Gunakan
    `websocat`, browser WebSocket API, atau `TestClient` dari Starlette.
    """
    await websocket.accept()

    db = _get_db_session()
    try:
        # --- 1. Validasi token ---
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            await websocket.send_text("[INFRAFORGE:ERROR] Token tidak valid.")
            await websocket.close(code=4001)
            return

        user_id_str = payload.get("sub")
        if user_id_str is None:
            await websocket.send_text("[INFRAFORGE:ERROR] Token tidak valid.")
            await websocket.close(code=4001)
            return

        try:
            user_id = int(user_id_str)
        except ValueError:
            await websocket.send_text("[INFRAFORGE:ERROR] Token tidak valid.")
            await websocket.close(code=4001)
            return

        user = auth_service.get_user_by_id(db, user_id)
        if user is None or not user.is_active:
            await websocket.send_text("[INFRAFORGE:ERROR] User tidak ditemukan atau tidak aktif.")
            await websocket.close(code=4001)
            return

        # --- 2. Validasi deployment ---
        dep = deployment_repository.get_by_id(db, deployment_id)
        if dep is None:
            await websocket.send_text("[INFRAFORGE:ERROR] Deployment tidak ditemukan.")
            await websocket.close(code=4004)
            return

        # Verifikasi kepemilikan: cek via application_id → project → owner
        # (import di sini untuk menghindari circular import)
        from app.repositories import application_repository  # noqa: PLC0415
        from app.services import project_service  # noqa: PLC0415

        app_obj = application_repository.get_by_id(db, dep.application_id)
        if app_obj is None:
            await websocket.send_text("[INFRAFORGE:ERROR] Deployment tidak ditemukan.")
            await websocket.close(code=4004)
            return

        project = project_service.get_project_by_id(db, app_obj.project_id)
        if project is None or project.owner_id != user_id:
            await websocket.send_text("[INFRAFORGE:ERROR] Akses ditolak.")
            await websocket.close(code=4003)
            return

        # --- 3. Tunggu log_path tersedia ---
        log_path = await _wait_for_log_path(deployment_id, db)
        if not log_path:
            # Deployment sudah terminal tapi tidak punya log file
            dep_now = deployment_repository.get_by_id(db, deployment_id)
            msg = (
                "[INFRAFORGE:ERROR] Log file tidak tersedia untuk deployment ini."
                if dep_now is None or dep_now.log_path is None
                else ""
            )
            if msg:
                await websocket.send_text(msg)
            await websocket.send_text(DONE_SENTINEL)
            await websocket.close()
            return

        # --- 4. Stream log file ---
        logger.info(
            f"WebSocket terhubung: streaming log deployment #{deployment_id} "
            f"ke user #{user_id}"
        )
        await _stream_log_file(websocket, log_path, deployment_id, db)

        await websocket.close()

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket terputus untuk deployment #{deployment_id}"
        )
    finally:
        db.close()
