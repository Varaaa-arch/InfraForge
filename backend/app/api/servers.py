"""
Router untuk manajemen server remote.

Endpoints:
  POST   /servers            → Tambah server baru
  GET    /servers            → Daftar server milik user
  GET    /servers/{id}       → Detail server
  PATCH  /servers/{id}       → Update server
  DELETE /servers/{id}       → Hapus server
  POST   /servers/{id}/test  → Tes koneksi SSH
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.server import Server
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.schemas.server import ServerCreate, ServerResponse, ServerUpdate, SSHTestResult
from app.services import server_service

router = APIRouter(prefix="/servers", tags=["servers"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_owned_server_or_404(db: Session, server_id: int, current_user: User) -> Server:
    """Ambil server milik user, raise 404 jika tidak ditemukan atau bukan miliknya."""
    server = server_service.get_server_for_owner(db, server_id, current_user.id)
    if not server:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found")
    return server


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[ServerResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Tambah server baru",
    description=(
        "Mendaftarkan server remote baru ke akun user. "
        "Credential SSH (password atau private_key) disimpan sesuai `auth_type` yang dipilih. "
        "Status awal server adalah **inactive** sampai koneksi berhasil diuji."
    ),
)
def create_server(
    payload: ServerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ServerResponse]:
    server = server_service.create_server(db, current_user.id, payload)
    log_audit("CREATE_SERVER", user=current_user.username, server=server.name)
    return ApiResponse(data=ServerResponse.model_validate(server))


@router.get(
    "",
    response_model=ApiResponse[list[ServerResponse]],
    summary="Daftar semua server",
    description="Menampilkan seluruh server yang terdaftar milik user yang sedang login.",
)
def list_servers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ServerResponse]]:
    servers = server_service.list_servers(db, current_user.id)
    return ApiResponse(data=[ServerResponse.model_validate(s) for s in servers])


@router.get(
    "/{server_id}",
    response_model=ApiResponse[ServerResponse],
    summary="Detail server",
    description="Menampilkan detail server berdasarkan ID. Hanya pemilik yang bisa mengakses.",
)
def get_server(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ServerResponse]:
    server = _get_owned_server_or_404(db, server_id, current_user)
    return ApiResponse(data=ServerResponse.model_validate(server))


@router.patch(
    "/{server_id}",
    response_model=ApiResponse[ServerResponse],
    summary="Update server",
    description=(
        "Mengupdate data server. Semua field bersifat opsional — "
        "hanya field yang dikirim yang akan diubah (partial update)."
    ),
)
def update_server(
    server_id: int,
    payload: ServerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ServerResponse]:
    server = _get_owned_server_or_404(db, server_id, current_user)
    updated = server_service.update_server(db, server, payload)
    log_audit("UPDATE_SERVER", user=current_user.username, server=updated.name)
    return ApiResponse(data=ServerResponse.model_validate(updated))


@router.delete(
    "/{server_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Hapus server",
    description="Menghapus server dari database secara permanen.",
)
def delete_server(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    server = _get_owned_server_or_404(db, server_id, current_user)
    name = server.name
    server_service.delete_server(db, server)
    log_audit("DELETE_SERVER", user=current_user.username, server=name)
    return ApiResponse(data=MessageResponse(message="Server deleted successfully"))


@router.post(
    "/{server_id}/test",
    response_model=ApiResponse[SSHTestResult],
    summary="Tes koneksi SSH",
    description=(
        "Mencoba membuka koneksi SSH ke server target. "
        "Status server akan diperbarui secara otomatis: **active** jika berhasil, "
        "**error** jika gagal. "
        "Response body berisi field `success` (bool) dan `message` (detail hasil)."
    ),
)
def test_server_connection(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[SSHTestResult]:
    server = _get_owned_server_or_404(db, server_id, current_user)
    result = server_service.test_server_connection(db, server)
    log_audit(
        "TEST_SERVER_CONNECTION",
        user=current_user.username,
        server=server.name,
        success=result.success,
    )
    return ApiResponse(data=result)
