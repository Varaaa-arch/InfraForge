"""
Pydantic schemas untuk GitHub webhook push event payload.

GitHub mengirim JSON body dengan struktur yang kompleks; kita hanya
membutuhkan sebagian field untuk memicu deployment:
  - ref           : branch yang di-push (format: "refs/heads/main")
  - repository     : info repo (url, full_name)
  - head_commit    : commit terbaru (id = SHA, message, timestamp)
  - delivery_id    : X-GitHub-Delivery header (di-pass sebagai parameter)

Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#push
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GitHubRepository(BaseModel):
    """Subset dari repository object di GitHub webhook payload."""

    model_config = ConfigDict(extra="ignore")

    full_name: str = Field(description="owner/repo, misal 'varaaa-arch/InfraForge'")
    html_url: str = Field(description="URL HTTPS repo, misal 'https://github.com/owner/repo'")
    clone_url: str | None = Field(
        default=None,
        description="URL untuk git clone (https://github.com/owner/repo.git)",
    )


class GitHubCommit(BaseModel):
    """Subset dari commit object di GitHub webhook payload."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Commit SHA (40 hex chars)")
    message: str = Field(default="")
    timestamp: datetime | None = Field(default=None)


class GitHubPushPayload(BaseModel):
    """
    Payload untuk event 'push' GitHub webhook.

    Hanya field yang dibutuhkan yang di-parse; sisanya diabaikan (extra=ignore)
    agar GitHub bisa menambah field baru tanpa break.
    """

    model_config = ConfigDict(extra="ignore")

    ref: str = Field(description="Ref yang di-push, misal 'refs/heads/main'")
    repository: GitHubRepository
    head_commit: GitHubCommit | None = Field(
        default=None,
        description="Commit terbaru. Bisa None untuk push yang menghapus branch.",
    )

    @property
    def branch(self) -> str:
        """Extract nama branch dari ref. 'refs/heads/main' → 'main'."""
        prefix = "refs/heads/"
        if self.ref.startswith(prefix):
            return self.ref[len(prefix):]
        # ref untuk tag: "refs/tags/v1.0" — kita tidak deploy tag
        return self.ref


class WebhookResponse(BaseModel):
    """Response standar untuk endpoint webhook."""

    accepted: bool = Field(description="True jika webhook diterima untuk diproses")
    message: str = Field(description="Pesan status")
    deployment_id: int | None = Field(
        default=None,
        description="ID deployment yang dibuat, jika ada",
    )
