"""Repository untuk tabel ``image_scans``."""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.models.image_scan import ImageScan, ImageScanStatus
from app.models.project import Project


def create(
    db: Session,
    *,
    image_name: str,
    project_id: int | None,
    requested_by: str | None,
) -> ImageScan:
    scan = ImageScan(
        image_name=image_name,
        project_id=project_id,
        requested_by=requested_by,
        status=ImageScanStatus.pending,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def get_by_id(db: Session, scan_id: int) -> ImageScan | None:
    return db.get(ImageScan, scan_id)


def _accessible_clause(user_id: int, username: str) -> ColumnElement[bool]:
    project_ids = select(Project.id).where(Project.owner_id == user_id)
    return or_(
        ImageScan.requested_by == username,
        ImageScan.project_id.in_(project_ids),
    )


def _conditions(
    *,
    user_id: int,
    username: str,
    is_admin: bool,
    project_id: int | None,
    image: str | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if project_id is not None:
        conditions.append(ImageScan.project_id == project_id)
    if image:
        conditions.append(ImageScan.image_name.ilike(f"%{image}%"))
    if not is_admin:
        conditions.append(_accessible_clause(user_id, username))
    return conditions


def list_scans(
    db: Session,
    *,
    user_id: int,
    username: str,
    is_admin: bool,
    project_id: int | None = None,
    image: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ImageScan], int]:
    conditions = _conditions(
        user_id=user_id,
        username=username,
        is_admin=is_admin,
        project_id=project_id,
        image=image,
    )
    total = int(
        db.execute(
            select(func.count()).select_from(ImageScan).where(*conditions)
        ).scalar_one()
    )
    rows = list(
        db.execute(
            select(ImageScan)
            .where(*conditions)
            .order_by(ImageScan.created_at.desc(), ImageScan.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return rows, total


def get_accessible_by_id(
    db: Session,
    scan_id: int,
    *,
    user_id: int,
    username: str,
    is_admin: bool,
) -> ImageScan | None:
    stmt = select(ImageScan).where(ImageScan.id == scan_id)
    if not is_admin:
        stmt = stmt.where(_accessible_clause(user_id, username))
    return db.execute(stmt).scalar_one_or_none()


def save(db: Session, scan: ImageScan) -> ImageScan:
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan
