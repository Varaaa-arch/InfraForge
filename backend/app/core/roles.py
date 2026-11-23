"""Definisi peran (RBAC) dan matriks izin InfraForge.

Modul ini sengaja tidak bergantung pada FastAPI maupun model database agar bisa
diimpor dari mana saja (model, service, dependency, skrip seed).
"""

import enum


DEFAULT_ROLE: str = "viewer"


class Role(str, enum.Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Permission(str, enum.Enum):
    PROJECT_WRITE = "project:write"
    SERVER_WRITE = "server:write"
    ENV_VAR_WRITE = "env_var:write"
    APPLICATION_WRITE = "application:write"
    IMAGE_WRITE = "image:write"
    IMAGE_SCAN = "image:scan"
    CONTAINER_LIFECYCLE = "container:lifecycle"
    CONTAINER_DELETE = "container:delete"
    DEPLOY = "deploy"
    ALERT_CHANNEL_WRITE = "alert_channel:write"
    USER_MANAGE = "user:manage"
    AUDIT_READ_ALL = "audit:read_all"
    TLS_DOMAIN_WRITE = "tls_domain:write"
    SECURITY_READ = "security:read"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    Role.ADMIN.value: frozenset(Permission),
    Role.DEVELOPER.value: frozenset(
        {
            Permission.PROJECT_WRITE,
            Permission.ENV_VAR_WRITE,
            Permission.APPLICATION_WRITE,
            Permission.IMAGE_WRITE,
            Permission.IMAGE_SCAN,
            Permission.CONTAINER_LIFECYCLE,
            Permission.DEPLOY,
            Permission.TLS_DOMAIN_WRITE,
            Permission.SECURITY_READ,
        }
    ),
    Role.VIEWER.value: frozenset({Permission.SECURITY_READ}),
}


def has_permission(role: str | None, permission: Permission) -> bool:
    """Cek apakah ``role`` memiliki ``permission`` sesuai matriks izin."""
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def role_label(role: str) -> str:
    """Label manusiawi untuk sebuah peran."""
    return {
        Role.ADMIN.value: "Admin",
        Role.DEVELOPER.value: "Developer",
        Role.VIEWER.value: "Viewer",
    }.get(role, role)
