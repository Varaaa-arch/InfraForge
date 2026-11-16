"""Repository untuk tabel ``container_policies``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.container_policy import ContainerPolicy


def get_by_name(db: Session, container_name: str) -> ContainerPolicy | None:
    return db.execute(
        select(ContainerPolicy).where(
            ContainerPolicy.container_name == container_name
        )
    ).scalar_one_or_none()


def list_all(db: Session) -> list[ContainerPolicy]:
    return list(
        db.execute(
            select(ContainerPolicy).order_by(ContainerPolicy.container_name)
        ).scalars()
    )


def list_for_project(db: Session, compose_project: str) -> list[ContainerPolicy]:
    return list(
        db.execute(
            select(ContainerPolicy).where(
                ContainerPolicy.compose_project == compose_project
            )
        ).scalars()
    )


def list_auto_heal_enabled(db: Session) -> list[ContainerPolicy]:
    return list(
        db.execute(
            select(ContainerPolicy).where(ContainerPolicy.auto_heal_enabled.is_(True))
        ).scalars()
    )


def create(
    db: Session,
    *,
    container_name: str,
    container_id: str | None = None,
    compose_project: str | None = None,
    compose_service: str | None = None,
) -> ContainerPolicy:
    policy = ContainerPolicy(
        container_name=container_name,
        container_id=container_id,
        compose_project=compose_project,
        compose_service=compose_service,
    )
    db.add(policy)
    db.flush()
    return policy


def delete(db: Session, policy: ContainerPolicy) -> None:
    db.delete(policy)
    db.flush()
