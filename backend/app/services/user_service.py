from sqlalchemy.orm import Session

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
