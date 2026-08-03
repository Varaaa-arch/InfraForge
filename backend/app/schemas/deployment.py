"""
Pydantic schemas untuk Deployment Flow (Task 3.6 + 3.7).

Schemas:
- DeploymentCreate  : payload POST /deployments
- DeploymentResponse: response publik semua endpoint, termasuk field `duration`
                      yang dihitung secara computed dari finished_at - started_at.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """
    Response publik untuk semua endpoint deployment.

    Field `duration` adalah computed field (bukan kolom DB) yang
    dihitung dari selisih `finished_at - started_at` dalam detik.
    Bernilai `None` jika deployment masih berjalan (finished_at belum diset).
    """

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
    duration: float | None = Field(
        default=None,
        description=(
            "Durasi deployment dalam detik. "
            "None jika deployment masih berjalan (finished_at belum diset)."
        ),
    )

    @model_validator(mode="after")
    def compute_duration(self) -> "DeploymentResponse":
        """Hitung durasi otomatis dari finished_at - started_at."""
        if self.finished_at is not None:
            delta = self.finished_at - self.started_at
            self.duration = round(delta.total_seconds(), 2)
        return self
