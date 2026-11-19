"""
Pydantic schemas untuk endpoint Application Management.

Tiga level schema:
- ApplicationCreate  : payload POST — wajib name + project_id, sisanya opsional
- ApplicationUpdate  : payload PATCH — semua field opsional (partial update)
- ApplicationResponse: response publik dari semua endpoint
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.application import AppStatus


def _validate_webhook_branches(value: list[str] | None) -> list[str] | None:
    """Validasi daftar branch webhook: unik, exact, dan tidak kosong."""
    if value is None:
        return None
    if not value:
        raise ValueError("webhook_branches minimal berisi satu branch")
    if len(value) > 20:
        raise ValueError("webhook_branches maksimal 20 branch")

    seen: set[str] = set()
    normalized: list[str] = []
    for branch in value:
        cleaned = branch.strip()
        if not cleaned:
            raise ValueError("branch pada webhook_branches tidak boleh kosong")
        if len(cleaned) > 100:
            raise ValueError("branch pada webhook_branches maksimal 100 karakter")
        if any(char.isspace() for char in cleaned):
            raise ValueError("branch pada webhook_branches tidak boleh mengandung spasi")
        if cleaned in seen:
            raise ValueError(f"branch duplikat pada webhook_branches: {cleaned}")
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


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
        description="Branch default yang akan di-deploy",
    )
    webhook_branches: list[str] | None = Field(
        default=None,
        description=(
            "Daftar branch exact yang memicu deployment webhook; "
            "kosong berarti memakai branch"
        ),
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
        if v is not None and not (v.startswith("https://") or v.startswith("http://") or v.startswith("file://")):
            raise ValueError("repository harus berupa URL valid (diawali http://, https://, atau file://)")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_no_spaces(cls, v: str) -> str:
        if " " in v.strip():
            raise ValueError("name tidak boleh mengandung spasi — gunakan tanda hubung (misal: backend-api)")
        return v.strip()

    @field_validator("webhook_branches")
    @classmethod
    def validate_webhook_branches(cls, v: list[str] | None) -> list[str] | None:
        return _validate_webhook_branches(v)


class ApplicationUpdate(BaseModel):
    """Payload PATCH — semua field opsional (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    repository: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, min_length=1, max_length=100)
    webhook_branches: list[str] | None = Field(default=None)
    dockerfile_path: str | None = Field(default=None, min_length=1, max_length=255)
    compose_path: str | None = Field(default=None, min_length=1, max_length=255)
    build_context: str | None = Field(default=None, max_length=255)
    status: AppStatus | None = None

    @field_validator("repository")
    @classmethod
    def validate_repository_url(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("https://") or v.startswith("http://") or v.startswith("file://")):
            raise ValueError("repository harus berupa URL valid (diawali http://, https://, atau file://)")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_no_spaces(cls, v: str | None) -> str | None:
        if v is not None and " " in v.strip():
            raise ValueError("name tidak boleh mengandung spasi")
        return v.strip() if v else v

    @field_validator("webhook_branches")
    @classmethod
    def validate_webhook_branches(cls, v: list[str] | None) -> list[str] | None:
        return _validate_webhook_branches(v)


class ApplicationResponse(BaseModel):
    """Response publik untuk semua endpoint aplikasi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    repository: str | None
    branch: str
    webhook_branches: list[str]
    dockerfile_path: str
    compose_path: str
    build_context: str | None
    status: AppStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("webhook_branches", mode="before")
    @classmethod
    def fallback_webhook_branches(
        cls, v: object, info: ValidationInfo
    ) -> list[str]:
        if v is None:
            return [str(info.data.get("branch", "main"))]
        if isinstance(v, list):
            normalized = _validate_webhook_branches(v)
            return normalized if normalized else [str(info.data.get("branch", "main"))]
        return [str(v)]


class LockStatusResponse(BaseModel):
    """Response untuk endpoint GET /applications/{id}/lock-status."""

    application_id: int = Field(description="ID aplikasi yang dicek")
    locked: bool = Field(description="True jika aplikasi sedang dalam proses deployment")
    running_deployment_id: int | None = Field(
        default=None,
        description="ID deployment yang sedang berjalan (dari Redis), jika ada",
    )
    app_status: AppStatus = Field(
        description="Status operasional aplikasi di database (idle/deploying/running/failed)"
    )
    lock_source: str = Field(
        description=(
            "Sumber informasi lock: 'redis' jika lock aktif di Redis, "
            "'db' jika status deploying di DB (Redis down), 'none' jika tidak locked"
        )
    )
