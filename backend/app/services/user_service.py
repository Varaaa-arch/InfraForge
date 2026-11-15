from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.user import User


def update_profile(
    db: Session,
    user: User,
    *,
    username: str | None = None,
    email: str | None = None,
    full_name: str | None = None,
) -> User:
    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    if full_name is not None:
        user.full_name = full_name

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user: User) -> User:
    user.is_active = False
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, *, limit: int = 100, offset: int = 0) -> list[User]:
    return db.query(User).order_by(User.id).offset(offset).limit(limit).all()


def count_admins(db: Session) -> int:
    return db.query(User).filter(User.role == Role.ADMIN.value).count()


def update_user_admin(
    db: Session,
    user: User,
    *,
    role: str | None = None,
    is_active: bool | None = None,
) -> User:
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active

    db.add(user)
    db.commit()
    db.refresh(user)
    return user
