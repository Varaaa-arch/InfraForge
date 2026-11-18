"""Repository layer untuk tabel ``deployment_tokens`` (CI/CD trigger token)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.deployment_token import DeploymentToken


def get_by_id(db: Session, token_id: int) -> DeploymentToken | None:
    """Ambil token berdasarkan primary key."""
    return db.get(DeploymentToken, token_id)


def get_by_id_and_project(
    db: Session, token_id: int, project_id: int
) -> DeploymentToken | None:
    """Ambil token yang dimiliki project tertentu."""
    return (
        db.query(DeploymentToken)
        .filter(
            DeploymentToken.id == token_id,
            DeploymentToken.project_id == project_id,
        )
        .first()
    )


def list_by_project(db: Session, project_id: int) -> list[DeploymentToken]:
    """Daftar token deployment milik sebuah project, terbaru dulu."""
    return (
        db.query(DeploymentToken)
        .filter(DeploymentToken.project_id == project_id)
        .order_by(DeploymentToken.created_at.desc(), DeploymentToken.id.desc())
        .all()
    )


def get_by_hash(db: Session, token_hash: str) -> DeploymentToken | None:
    """Cari token berdasarkan hash SHA-256."""
    return (
        db.query(DeploymentToken)
        .filter(DeploymentToken.token_hash == token_hash)
        .first()
    )


def create(
    db: Session,
    *,
    project_id: int,
    created_by: int | None,
    name: str,
    token_hash: str,
    prefix: str,
    expires_at: datetime | None,
    application_id: int | None = None,
) -> DeploymentToken:
    """Buat token deployment baru. Commit dan refresh dilakukan di sini."""
    token = DeploymentToken(
        project_id=project_id,
        application_id=application_id,
        created_by=created_by,
        name=name,
        token_hash=token_hash,
        prefix=prefix,
        expires_at=expires_at,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def revoke(db: Session, token: DeploymentToken, when: datetime) -> DeploymentToken:
    """Cabut token dengan mengisi ``revoked_at``."""
    token.revoked_at = when
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def update_last_used(
    db: Session, token: DeploymentToken, when: datetime
) -> None:
    """Perbarui ``last_used_at`` token."""
    token.last_used_at = when
    db.add(token)
    db.commit()
