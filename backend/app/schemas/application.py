"""
Pydantic schemas untuk endpoint Application Management.

Tiga level schema:
- ApplicationCreate  : payload POST — wajib name + project_id, sisanya opsional
- ApplicationUpdate  : payload PATCH — semua field opsional (partial update)
- ApplicationResponse: response publik dari semua endpoint
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.application import AppStatus


class ApplicationCreate(BaseModel):
    """Payload untuk mendaftarkan aplikasi baru."""

    project_id: int = Field(description="ID project pemilik aplikasi ini")
    name: str = Field(
        min_length=1,
        max_length=100,
        description="Nama unik aplikasi dalam project (misal: backend-api, worker)",
    )
    repository: str | None = Field(
        default=None,
        max_length=500,
        description="URL repository Git (https://github.com/org/repo)",
    )
    branch: str = Field(
        default="main",
        min_length=1,
        max_length=100,
        description="Branch yang akan di-deploy",
    )
    dockerfile_path: str = Field(
        default="Dockerfile",
        min_length=1,
        max_length=255,
        description="Path ke Dockerfile relatif dari root repository",
    )
    compose_path: str = Field(
        default="docker-compose.yml",
        min_length=1,
        max_length=255,
        description="Path ke docker-compose file",
    )
    build_context: str | None = Field(
        default=None,
        max_length=255,
        description="Docker build context path (opsional)",
    )

    @field_validator("repository")
    @classmethod
    def validate_repository_url(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("repository harus berupa URL valid (diawali http:// atau https://)")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_no_spaces(cls, v: str) -> str:
        if " " in v.strip():
            raise ValueError("name tidak boleh mengandung spasi — gunakan tanda hubung (misal: backend-api)")
        return v.strip()


class ApplicationUpdate(BaseModel):
    """Payload PATCH — semua field opsional (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    repository: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, min_length=1, max_length=100)
    dockerfile_path: str | None = Field(default=None, min_length=1, max_length=255)
    compose_path: str | None = Field(default=None, min_length=1, max_length=255)
    build_context: str | None = Field(default=None, max_length=255)
    status: AppStatus | None = None

    @field_validator("repository")
    @classmethod
    def validate_repository_url(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("repository harus berupa URL valid (diawali http:// atau https://)")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_no_spaces(cls, v: str | None) -> str | None:
        if v is not None and " " in v.strip():
            raise ValueError("name tidak boleh mengandung spasi")
        return v.strip() if v else v


class ApplicationResponse(BaseModel):
    """Response publik untuk semua endpoint aplikasi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    repository: str | None
    branch: str
    dockerfile_path: str
    compose_path: str
    build_context: str | None
    status: AppStatus
    created_at: datetime
    updated_at: datetime
