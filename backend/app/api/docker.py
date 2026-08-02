"""
Router untuk manajemen Docker Images (Task 3.4).

Endpoints:
  GET    /docker/images              → Daftar image lokal
  POST   /docker/images/pull         → Pull image dari registry
  DELETE /docker/images/{image_id}   → Hapus image
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.services import docker_service

router = APIRouter(prefix="/docker", tags=["docker"])


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------

class ImageResponse(BaseModel):
    id: str
    tags: list[str]
    size: int = Field(description="Ukuran image dalam bytes")
    created: str


class PullRequest(BaseModel):
    image: str = Field(min_length=1, description="Nama image, misal: nginx, python")
    tag: str = Field(default="latest", min_length=1, description="Tag image")


class PullResponse(BaseModel):
    image: str
    tag: str
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/images",
    response_model=ApiResponse[list[ImageResponse]],
    summary="Daftar Docker images lokal",
    description="Menampilkan semua Docker image yang tersedia di Docker daemon lokal.",
)
def list_images(
    _: User = Depends(get_current_user),
) -> ApiResponse[list[ImageResponse]]:
    try:
        images = docker_service.list_images()
        return ApiResponse(
            data=[
                ImageResponse(id=img.id, tags=img.tags, size=img.size, created=img.created)
                for img in images
            ]
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.post(
    "/images/pull",
    response_model=ApiResponse[PullResponse],
    summary="Pull Docker image dari registry",
    description="Mengunduh Docker image dari Docker Hub atau registry lain.",
)
def pull_image(
    payload: PullRequest,
    _: User = Depends(get_current_user),
) -> ApiResponse[PullResponse]:
    try:
        result = docker_service.pull_image(payload.image, payload.tag)
        return ApiResponse(
            data=PullResponse(
                image=result.image,
                tag=result.tag,
                success=result.success,
                message=result.message,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.delete(
    "/images/{image_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Hapus Docker image",
    description=(
        "Menghapus Docker image berdasarkan ID atau nama:tag. "
        "Gunakan `?force=true` untuk memaksa hapus meski ada container yang masih pakai."
    ),
)
def remove_image(
    image_id: str,
    force: bool = Query(default=False, description="Paksa hapus image"),
    _: User = Depends(get_current_user),
) -> ApiResponse[MessageResponse]:
    try:
        docker_service.remove_image(image_id, force=force)
        return ApiResponse(data=MessageResponse(message=f"Image {image_id} berhasil dihapus"))
    except RuntimeError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "tidak ditemukan" in detail
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        raise HTTPException(code, detail)
