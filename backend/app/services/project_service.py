from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.project import GitProvider, Project, Visibility
from app.utils.slugify import slugify


def _generate_unique_slug(db: Session, name: str) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 1
    while db.query(Project).filter(Project.slug == slug).first() is not None:
        counter += 1
        slug = f"{base_slug}-{counter}"
    return slug


def create_project(
    db: Session,
    owner_id: int,
    name: str,
    description: str | None,
    visibility: Visibility,
) -> Project:
    project = Project(
        owner_id=owner_id,
        name=name,
        slug=_generate_unique_slug(db, name),
        description=description,
        visibility=visibility,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project_by_id(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def list_projects_for_owner(db: Session, owner_id: int) -> list[Project]:
    return (
        db.query(Project)
        .filter(Project.owner_id == owner_id)
        .order_by(Project.created_at.desc())
        .all()
    )

def count_projects_for_owner(db: Session, owner_id: int) -> int:
    return db.query(Project).filter(Project.owner_id == owner_id).count()

def update_project(
    db: Session,
    project: Project,
    *,
    name: str | None = None,
    description: str | None = None,
    visibility: Visibility | None = None,
) -> Project:
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if visibility is not None:
        project.visibility = visibility

    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_repository(
    db: Session,
    project: Project,
    *,
    repository_url: str,
    default_branch: str,
    provider: GitProvider,
) -> Project:
    project.repository_url = repository_url
    project.default_branch = default_branch
    project.provider = provider
    project.repository_connected_at = datetime.now(timezone.utc)

    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()
