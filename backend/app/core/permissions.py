"""Dependency FastAPI untuk penegakan RBAC di endpoint.

Pemakaian di route::

    current_user: User = Depends(require_permission(Permission.DEPLOY))

Dependency ini meresolusi user dari token (JWT/PAT) lalu memastikan peran user
memiliki izin yang diminta. Bila tidak, endpoint mengembalikan HTTP 403.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.roles import Permission, has_permission
from app.models.user import User


def require_permission(permission: Permission) -> Callable[..., User]:
    """Buat dependency yang mewajibkan sebuah izin tertentu."""

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Peran '{current_user.role}' tidak memiliki izin "
                    f"'{permission.value}' untuk aksi ini"
                ),
            )
        return current_user

    return _dependency


require_admin = require_permission(Permission.USER_MANAGE)
