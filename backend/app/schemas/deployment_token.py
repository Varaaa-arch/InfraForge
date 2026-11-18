"""Schema deployment token (CI/CD trigger) dan endpoint publik trigger."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentStatus


class DeploymentTokenCreate(BaseModel):
    """Payload untuk membuat deployment token sebuah project."""

    name: str = Field(
        min_length=1,
        max_length=100,
        description="Label token, misal: GitHub Actions backend",
    )
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Masa berlaku token dalam hari (kosong = tanpa kedaluwarsa)",
    )
    application_id: int | None = Field(
        default=None,
        description=(
            "ID aplikasi dalam project. Kosong = token berlaku untuk seluruh "
            "project; terisi = token hanya untuk aplikasi tersebut."
        ),
    )


class DeploymentTokenResponse(BaseModel):
    """Metadata token — plaintext dan hash tidak pernah dikembalikan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    application_id: int | None
    name: str
    prefix: str
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class DeploymentTokenCreated(DeploymentTokenResponse):
    """Response pembuatan token — plaintext hanya tampil sekali."""

    token: str


class DeploymentTriggerRequest(BaseModel):
    """Body opsional endpoint publik ``POST /deploy/trigger/{token}``."""

    application_id: int | None = Field(
        default=None,
        description=(
            "ID aplikasi dalam project. Wajib bila project memiliki lebih dari "
            "satu aplikasi."
        ),
    )
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Override branch yang di-deploy (default: branch aplikasi)",
    )
    server_id: int | None = Field(
        default=None,
        description=(
            "ID server target milik owner project. Default: server pertama owner."
        ),
    )


class DeploymentTriggerResponse(BaseModel):
    """Ringkasan deployment yang dijadwalkan dari trigger token."""

    deployment_id: int
    application_id: int
    application_name: str
    branch: str
    status: DeploymentStatus
    message: str


class DeploymentScheduledItem(BaseModel):
    """Satu deployment yang berhasil dijadwalkan dari event webhook."""

    deployment_id: int
    application_id: int
    application_name: str
    branch: str
    status: DeploymentStatus


class DeployWebhookResponse(BaseModel):
    """Ringkasan penerimaan webhook deployment (CI/GitHub/GitLab)."""

    accepted: bool
    message: str
    source: str = Field(description="github | gitlab | ci")
    event: str | None = Field(default=None, description="Contoh: push")
    branch: str | None = None
    deployment_ids: list[int] = Field(default_factory=list)
    deployments: list[DeploymentScheduledItem] = Field(default_factory=list)
    skipped_application_ids: list[int] = Field(default_factory=list)
