"""Service webhook deployment per-project (GitHub, GitLab, dan CI sederhana).

Endpoint publik menerima tiga bentuk request:

- **GitHub native** — header ``X-GitHub-Event`` + ``X-Hub-Signature-256``;
  signature HMAC-SHA256 diverifikasi dengan deployment token sebagai secret.
- **GitLab native** — header ``X-Gitlab-Event`` + ``X-Gitlab-Token``;
  nilai token dibandingkan constant-time dengan token pada path.
- **CI sederhana** — tanpa header event; body JSON opsional berisi
  ``application_id``, ``branch``, dan ``server_id``.

Webhook native memetakan repository + branch pada payload ke aplikasi dalam
scope token. Token project-wide dapat menjadwalkan beberapa aplikasi sekaligus;
token aplikasi hanya boleh memicu aplikasi yang terikat.
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.models.application import Application
from app.models.deployment import Deployment
from app.models.deployment_token import DeploymentToken
from app.models.project import Project
from app.models.server import Server
from app.repositories import application_repository
from app.schemas.deployment_token import DeploymentTriggerRequest
from app.services import (
    application_service,
    deployment_token_service,
    project_service,
    webhook_service,
)

GITHUB_EVENT_HEADER = "x-github-event"
GITHUB_SIGNATURE_HEADER = "x-hub-signature-256"
GITHUB_DELIVERY_HEADER = "x-github-delivery"
GITLAB_EVENT_HEADER = "x-gitlab-event"
GITLAB_TOKEN_HEADER = "x-gitlab-token"
GITLAB_DELIVERY_HEADER = "x-gitlab-event-uuid"
IDEMPOTENCY_HEADER = "idempotency-key"


class InvalidWebhookSignature(Exception):
    """Signature/secret webhook tidak valid atau tidak lengkap."""


class InvalidWebhookPayload(Exception):
    """Body webhook bukan JSON yang valid atau tidak sesuai schema."""


@dataclass(frozen=True)
class ParsedWebhook:
    """Hasil parsing request webhook yang sudah terautentikasi."""

    source: str
    event: str | None
    branch: str | None
    repository: str | None
    commit_sha: str | None
    delivery_id: str | None
    request: DeploymentTriggerRequest | None = None


@dataclass
class ScheduledDeployment:
    """Deployment yang berhasil dibuat dari sebuah event webhook."""

    deployment: Deployment
    application: Application
    server: Server


def detect_source(headers: Headers) -> str:
    """Tebak sumber request dari header (github | gitlab | ci)."""
    if headers.get(GITHUB_EVENT_HEADER) or headers.get(GITHUB_SIGNATURE_HEADER):
        return "github"
    if headers.get(GITLAB_EVENT_HEADER) or headers.get(GITLAB_TOKEN_HEADER):
        return "gitlab"
    return "ci"


def _json_object(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidWebhookPayload("Payload bukan JSON valid") from exc
    if not isinstance(data, dict):
        raise InvalidWebhookPayload("Payload webhook harus berupa objek JSON")
    return data


def _extract_branch(ref: object) -> str | None:
    if not isinstance(ref, str):
        return None
    return webhook_service.extract_branch(ref)


def _first_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_github(
    headers: Headers, raw_body: bytes, token: str
) -> ParsedWebhook:
    event = headers.get(GITHUB_EVENT_HEADER)
    signature = headers.get(GITHUB_SIGNATURE_HEADER)
    if not event or not signature:
        raise InvalidWebhookSignature(
            "Header X-GitHub-Event dan X-Hub-Signature-256 wajib lengkap"
        )
    if not webhook_service.verify_signature_with_secret(raw_body, signature, token):
        raise InvalidWebhookSignature("Signature GitHub tidak valid")

    delivery = headers.get(GITHUB_DELIVERY_HEADER)
    delivery_id = f"github:{delivery}" if delivery else None

    if event != "push":
        return ParsedWebhook(
            source="github",
            event=event,
            branch=None,
            repository=None,
            commit_sha=None,
            delivery_id=delivery_id,
        )

    payload = _json_object(raw_body)
    repository = payload.get("repository")
    repo_url = None
    if isinstance(repository, dict):
        repo_url = _first_str(repository, "html_url", "clone_url", "url")

    head_commit = payload.get("head_commit")
    commit_sha = None
    if isinstance(head_commit, dict):
        commit_sha = _first_str(head_commit, "id")

    return ParsedWebhook(
        source="github",
        event=event,
        branch=_extract_branch(payload.get("ref")),
        repository=repo_url,
        commit_sha=commit_sha,
        delivery_id=delivery_id,
    )


def _parse_gitlab(
    headers: Headers, raw_body: bytes, token: str
) -> ParsedWebhook:
    event = headers.get(GITLAB_EVENT_HEADER)
    secret = headers.get(GITLAB_TOKEN_HEADER)
    if not event or not secret:
        raise InvalidWebhookSignature(
            "Header X-Gitlab-Event dan X-Gitlab-Token wajib lengkap"
        )
    if not hmac.compare_digest(secret, token):
        raise InvalidWebhookSignature("Secret GitLab tidak valid")

    delivery = headers.get(GITLAB_DELIVERY_HEADER) or headers.get(
        IDEMPOTENCY_HEADER
    )
    delivery_id = f"gitlab:{delivery}" if delivery else None

    payload = _json_object(raw_body)
    object_kind = payload.get("object_kind")
    is_push = object_kind == "push" or "push" in event.lower()
    if not is_push:
        return ParsedWebhook(
            source="gitlab",
            event=event,
            branch=None,
            repository=None,
            commit_sha=None,
            delivery_id=delivery_id,
        )
    event = "push"

    repository = payload.get("repository")
    repo_url = None
    if isinstance(repository, dict):
        repo_url = _first_str(repository, "git_http_url", "homepage", "url")
    if repo_url is None:
        project = payload.get("project")
        if isinstance(project, dict):
            repo_url = _first_str(project, "git_http_url", "web_url")

    commit_sha = _first_str(payload, "checkout_sha", "after")
    if commit_sha is None:
        commits = payload.get("commits")
        if isinstance(commits, list) and commits:
            last = commits[-1]
            if isinstance(last, dict):
                commit_sha = _first_str(last, "id")

    return ParsedWebhook(
        source="gitlab",
        event=event,
        branch=_extract_branch(payload.get("ref")),
        repository=repo_url,
        commit_sha=commit_sha,
        delivery_id=delivery_id,
    )


def _parse_ci(headers: Headers, raw_body: bytes) -> ParsedWebhook:
    payload = _json_object(raw_body)
    try:
        request = DeploymentTriggerRequest.model_validate(payload)
    except ValidationError as exc:
        raise InvalidWebhookPayload(
            f"Payload trigger tidak valid: {exc.errors()[0]['msg']}"
        ) from exc

    delivery = headers.get(IDEMPOTENCY_HEADER)
    return ParsedWebhook(
        source="ci",
        event=None,
        branch=request.branch,
        repository=None,
        commit_sha=None,
        delivery_id=f"ci:{delivery}" if delivery else None,
        request=request,
    )


def parse_webhook_request(
    headers: Headers, raw_body: bytes, token: str
) -> ParsedWebhook:
    """Parse request webhook dan verifikasi kredensial sesuai sumbernya.

    Raises:
        InvalidWebhookSignature: signature/secret tidak valid.
        InvalidWebhookPayload: body bukan JSON/schema yang valid.
    """
    source = detect_source(headers)
    if source == "github":
        return _parse_github(headers, raw_body, token)
    if source == "gitlab":
        return _parse_gitlab(headers, raw_body, token)
    return _parse_ci(headers, raw_body)


def _matches_application(application: Application, parsed: ParsedWebhook) -> bool:
    if application.repository is None:
        return False
    if parsed.repository is None or parsed.branch is None:
        return False
    return (
        webhook_service.normalize_repo_url(application.repository)
        == webhook_service.normalize_repo_url(parsed.repository)
        and application.branch == parsed.branch
    )


def resolve_applications(
    db: Session, token: DeploymentToken, parsed: ParsedWebhook
) -> tuple[Project, Server, list[Application]]:
    """Resolve project, server, dan aplikasi target untuk sebuah event.

    Token aplikasi hanya menghasilkan aplikasi yang terikat (bila repo/branch
    event cocok). Token project-wide memilih semua aplikasi yang cocok.

    Raises:
        ValueError: project/server/aplikasi tidak ditemukan atau ambigu.
    """
    project = project_service.get_project_by_id(db, token.project_id)
    if project is None:
        raise ValueError("Project dari token tidak ditemukan")

    if parsed.source == "ci":
        request = parsed.request or DeploymentTriggerRequest()
        _project, application, server = deployment_token_service.resolve_target(
            db,
            token,
            application_id=request.application_id,
            server_id=request.server_id,
        )
        return project, server, [application]

    server = deployment_token_service.resolve_server(
        db, project.owner_id, parsed.request.server_id if parsed.request else None
    )

    if token.application_id is not None:
        scoped_application = application_repository.get_by_id_and_project(
            db, token.application_id, project.id
        )
        if scoped_application is None or not _matches_application(
            scoped_application, parsed
        ):
            return project, server, []
        return project, server, [scoped_application]

    applications = application_service.list_applications_by_project(db, project.id)
    return project, server, [
        application
        for application in applications
        if _matches_application(application, parsed)
    ]


def trigger_applications(
    db: Session,
    token: DeploymentToken,
    applications: list[Application],
    server: Server,
    *,
    branch: str | None,
    tag: str | None = None,
) -> list[ScheduledDeployment]:
    """Buat deployment record untuk setiap aplikasi target."""
    scheduled: list[ScheduledDeployment] = []
    for application in applications:
        deployment = deployment_token_service.trigger_deployment(
            db,
            token,
            application,
            server,
            branch=branch,
            tag=tag,
        )
        scheduled.append(
            ScheduledDeployment(
                deployment=deployment,
                application=application,
                server=server,
            )
        )
    return scheduled


def audit_details(parsed: ParsedWebhook) -> dict[str, str]:
    """Detail audit yang aman (tanpa token) untuk event webhook."""
    details: dict[str, str] = {"source": parsed.source}
    if parsed.event:
        details["event"] = parsed.event
    if parsed.branch:
        details["branch"] = parsed.branch
    if parsed.repository:
        details["repository"] = parsed.repository[:255]
    if parsed.commit_sha:
        details["commit_sha"] = parsed.commit_sha[:40]
    if parsed.delivery_id:
        details["delivery_id"] = parsed.delivery_id[:100]
    return details


def dedup_key(parsed: ParsedWebhook) -> str | None:
    """Kembalikan delivery key yang sudah diberi prefiks sumber."""
    return parsed.delivery_id
