"""
Pydantic schemas untuk Deployment Flow (Task 3.6).

Tiga schema utama:
- DeploymentCreate  : payload POST /deployments (trigger deployment baru)
- DeploymentResponse: response publik semua endpoint deployment
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentStatus


class DeploymentCreate(BaseModel):
    """
    Payload untuk memicu deployment baru.

    `branch` opsional — jika tidak diberikan, service akan menggunakan
    branch yang dikonfigurasi di Application.
    """

    application_id: int = Field(description="ID aplikasi yang akan di-deploy")
    server_id: int = Field(description="ID server target deployment")
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Override branch yang akan di-deploy. "
            "Jika kosong, gunakan branch default dari konfigurasi aplikasi."
        ),
    )


class DeploymentResponse(BaseModel):
    """Response publik untuk semua endpoint deployment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    server_id: int | None
    status: DeploymentStatus
    branch: str
    commit_sha: str | None
    log_path: str | None
    started_at: datetime
    finished_at: datetime | None
