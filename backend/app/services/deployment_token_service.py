"""Service deployment token (CI/CD trigger) per project.

Format token: ``dt_<prefix>_<secret>``.
- ``prefix`` (8 hex char) disimpan untuk ditampilkan di UI.
- Hanya **hash SHA-256** dari token lengkap yang disimpan di database.
- Token plaintext hanya dikembalikan sekali saat dibuat.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.deployment import Deployment, TriggerSource
from app.models.deployment_token import DeploymentToken
from app.models.project import Project
from app.models.server import Server
from app.repositories import (
    application_repository,
    deployment_token_repository,
    server_repository,
)
from app.services import application_service, deployment_service, project_service

TOKEN_PREFIX = "dt_"
LAST_USED_THROTTLE = timedelta(seconds=60)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(
    db: Session,
    *,
    project_id: int,
    created_by: int | None,
    name: str,
    expires_in_days: int | None = None,
    application_id: int | None = None,
) -> tuple[DeploymentToken, str]:
    """Buat token baru dan kembalikan ``(record, token_plaintext)``.

    Raises:
        ValueError: ``application_id`` tidak ditemukan pada project.
    """
    if application_id is not None:
        application = application_repository.get_by_id_and_project(
            db, application_id, project_id
        )
        if application is None:
            raise ValueError(
                f"Application {application_id} tidak ditemukan pada project ini"
            )

    token_prefix = secrets.token_hex(4)
    secret = secrets.token_hex(32)
    token = f"{TOKEN_PREFIX}{token_prefix}_{secret}"

    expires_at = (
        _now() + timedelta(days=expires_in_days)
        if expires_in_days is not None
        else None
    )

    record = deployment_token_repository.create(
        db,
        project_id=project_id,
        application_id=application_id,
        created_by=created_by,
        name=name,
        token_hash=hash_token(token),
        prefix=f"{TOKEN_PREFIX}{token_prefix}",
        expires_at=expires_at,
    )
    return record, token


def list_tokens(db: Session, project_id: int) -> list[DeploymentToken]:
    return deployment_token_repository.list_by_project(db, project_id)


def get_token(db: Session, project_id: int, token_id: int) -> DeploymentToken | None:
    return deployment_token_repository.get_by_id_and_project(db, token_id, project_id)


def revoke_token(db: Session, token: DeploymentToken) -> DeploymentToken:
    return deployment_token_repository.revoke(db, token, _now())


def find_active_by_token(db: Session, token: str) -> DeploymentToken | None:
    """Cari token aktif (belum dicabut & belum kedaluwarsa) berdasarkan hash."""
    record = deployment_token_repository.get_by_hash(db, hash_token(token))
    if record is None:
        return None
    if record.revoked_at is not None:
        return None
    now = _now()
    if record.expires_at is not None and record.expires_at <= now:
        return None
    return record


def touch_last_used(db: Session, token: DeploymentToken) -> None:
    """Perbarui ``last_used_at`` (dibatasi sekali per menit agar hemat write)."""
    now = _now()
    if token.last_used_at is not None:
        last_used = token.last_used_at
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        if now - last_used < LAST_USED_THROTTLE:
            return

    deployment_token_repository.update_last_used(db, token, now)


def _resolve_application(
    db: Session, project_id: int, application_id: int | None
) -> Application:
    """Pilih aplikasi target berdasarkan isi body trigger.

    Raises:
        ValueError: project belum punya aplikasi, application_id tidak ada di
            project, atau project punya >1 aplikasi tanpa application_id.
    """
    applications = application_service.list_applications_by_project(db, project_id)
    if not applications:
        raise ValueError("Project belum memiliki aplikasi yang bisa di-deploy")

    if application_id is not None:
        for app in applications:
            if app.id == application_id:
                return app
        raise ValueError(
            f"Application {application_id} tidak ditemukan pada project ini"
        )

    if len(applications) > 1:
        listing = ", ".join(f"{app.id}={app.name}" for app in applications)
        raise ValueError(
            "Project memiliki lebih dari satu aplikasi; sertakan application_id "
            f"({listing})"
        )
    return applications[0]


def resolve_server(
    db: Session, owner_id: int, server_id: int | None
) -> Server:
    """Pilih server target: body override (harus milik owner) atau server pertama."""
    if server_id is not None:
        server = server_repository.get_by_id_and_owner(db, server_id, owner_id)
        if server is None:
            raise ValueError(f"Server {server_id} tidak ditemukan")
        return server

    servers = server_repository.list_by_owner(db, owner_id)
    if not servers:
        raise ValueError("Owner project belum memiliki server target")
    return servers[0]


def _resolve_scoped_application(
    db: Session, project_id: int, application_id: int
) -> Application:
    """Ambil aplikasi yang dikunci oleh token dan pastikan masih milik project."""
    application = application_repository.get_by_id_and_project(
        db, application_id, project_id
    )
    if application is None:
        raise ValueError("Aplikasi yang terikat pada token tidak ditemukan")
    return application


def resolve_target(
    db: Session,
    token: DeploymentToken,
    *,
    application_id: int | None = None,
    server_id: int | None = None,
) -> tuple[Project, Application, Server]:
    """Resolusi project, aplikasi, dan server target untuk sebuah token.

    Token aplikasi mengunci target; body ``application_id`` yang berbeda
    ditolak. Token project-wide mengikuti aturan lama (wajib eksplisit bila
    project punya lebih dari satu aplikasi).

    Raises:
        ValueError: project/aplikasi/server tidak ditemukan atau ambigu.
    """
    project = project_service.get_project_by_id(db, token.project_id)
    if project is None:
        raise ValueError("Project dari token tidak ditemukan")

    if token.application_id is not None:
        application = _resolve_scoped_application(
            db, project.id, token.application_id
        )
        if application_id is not None and application_id != token.application_id:
            raise ValueError(
                "Token ini hanya berlaku untuk application "
                f"{token.application_id}"
            )
    else:
        application = _resolve_application(db, project.id, application_id)

    server = resolve_server(db, project.owner_id, server_id)
    return project, application, server


def trigger_deployment(
    db: Session,
    token: DeploymentToken,
    application: Application,
    server: Server,
    *,
    branch: str | None = None,
    tag: str | None = None,
) -> Deployment:
    """Buat deployment record (status pending) dari trigger token CI/CD."""
    deployment, _app, _server = deployment_service.create_deployment_record(
        db,
        application.id,
        server.id,
        branch_override=branch,
        trigger_source=TriggerSource.ci_token.value,
        tag=tag,
        triggered_by=f"deploy-token:{token.name}",
    )
    touch_last_used(db, token)
    return deployment
