"""Middleware audit log otomatis.

Setiap request yang cocok dengan salah satu aturan di ``AUDIT_RULES`` dicatat
ke tabel ``audit_logs`` setelah response selesai diproses. Pendekatan ini
menjamin aksi baru yang melalui rute terdaftar langsung teraudit tanpa perlu
menambah pemanggilan manual di endpoint.

Prinsip:
- Hanya rute sensitif (mutasi + reveal secret) yang dicatat — lihat allowlist.
- Body request **tidak pernah** disimpan (menghindari bocornya password/secret).
- Kegagalan menulis audit tidak boleh menggagalkan request utama.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services import audit_service


@dataclass(frozen=True)
class AuditRule:
    method: str
    pattern: re.Pattern[str]
    action: str
    resource_type: str | None = None


def _rule(
    method: str, path: str, action: str, resource_type: str | None = None
) -> AuditRule:
    return AuditRule(
        method=method,
        pattern=re.compile(rf"^{path}/?$"),
        action=action,
        resource_type=resource_type,
    )


AUDIT_RULES: tuple[AuditRule, ...] = (
    # Auth & akun
    _rule("POST", r"/auth/register", "AUTH_REGISTER", "user"),
    _rule("POST", r"/auth/login", "AUTH_LOGIN", "user"),
    _rule("POST", r"/auth/logout", "AUTH_LOGOUT", "user"),
    _rule("POST", r"/auth/change-password", "PASSWORD_CHANGE", "user"),
    _rule("PATCH", r"/users/me", "UPDATE_PROFILE", "user"),
    _rule("DELETE", r"/users/me", "DEACTIVATE_ACCOUNT", "user"),
    _rule("PATCH", r"/users/(?P<id>\d+)", "UPDATE_USER", "user"),
    # Personal access token
    _rule("POST", r"/api-tokens", "API_TOKEN_CREATE", "api_token"),
    _rule("DELETE", r"/api-tokens/(?P<id>\d+)", "API_TOKEN_REVOKE", "api_token"),
    # Project & repository
    _rule("POST", r"/projects", "PROJECT_CREATE", "project"),
    _rule("PATCH", r"/projects/(?P<id>\d+)", "PROJECT_UPDATE", "project"),
    _rule(
        "PATCH",
        r"/projects/(?P<id>\d+)/repository",
        "PROJECT_REPOSITORY_UPDATE",
        "project",
    ),
    _rule("DELETE", r"/projects/(?P<id>\d+)", "PROJECT_DELETE", "project"),
    # Environment variables (reveal ikut diaudit walau method GET)
    _rule(
        "POST",
        r"/projects/(?P<project_id>\d+)/env",
        "ENV_VAR_BULK_UPSERT",
        "env_var",
    ),
    _rule(
        "GET",
        r"/projects/(?P<project_id>\d+)/env/(?P<id>\d+)",
        "ENV_VAR_REVEAL",
        "env_var",
    ),
    _rule(
        "PATCH",
        r"/projects/(?P<project_id>\d+)/env/(?P<id>\d+)",
        "ENV_VAR_UPDATE",
        "env_var",
    ),
    _rule(
        "DELETE",
        r"/projects/(?P<project_id>\d+)/env/(?P<id>\d+)",
        "ENV_VAR_DELETE",
        "env_var",
    ),
    # Server
    _rule("POST", r"/servers", "SERVER_CREATE", "server"),
    _rule("PATCH", r"/servers/(?P<id>\d+)", "SERVER_UPDATE", "server"),
    _rule("DELETE", r"/servers/(?P<id>\d+)", "SERVER_DELETE", "server"),
    _rule("POST", r"/servers/(?P<id>\d+)/test", "SERVER_TEST_CONNECTION", "server"),
    # Application
    _rule("POST", r"/applications", "APPLICATION_CREATE", "application"),
    _rule(
        "PATCH", r"/applications/(?P<id>\d+)", "APPLICATION_UPDATE", "application"
    ),
    _rule(
        "DELETE", r"/applications/(?P<id>\d+)", "APPLICATION_DELETE", "application"
    ),
    # Docker image
    _rule("POST", r"/docker/images/pull", "IMAGE_PULL", "docker_image"),
    _rule("DELETE", r"/docker/images/(?P<id>[^/]+)", "IMAGE_DELETE", "docker_image"),
    # Container lifecycle
    _rule(
        "POST", r"/containers/(?P<id>[^/]+)/start", "CONTAINER_START", "container"
    ),
    _rule("POST", r"/containers/(?P<id>[^/]+)/stop", "CONTAINER_STOP", "container"),
    _rule(
        "POST",
        r"/containers/(?P<id>[^/]+)/restart",
        "CONTAINER_RESTART",
        "container",
    ),
    _rule("DELETE", r"/containers/(?P<id>[^/]+)", "CONTAINER_DELETE", "container"),
    _rule(
        "PUT",
        r"/containers/(?P<id>[^/]+)/policy",
        "CONTAINER_POLICY_UPDATE",
        "container",
    ),
    _rule(
        "DELETE",
        r"/containers/(?P<id>[^/]+)/policy",
        "CONTAINER_POLICY_DELETE",
        "container",
    ),
    # Deployment
    _rule("POST", r"/deployments", "DEPLOY", "deployment"),
    _rule("POST", r"/deployments/(?P<id>\d+)/rollback", "ROLLBACK", "deployment"),
    _rule(
        "POST",
        r"/deployments/(?P<id>\d+)/health-check",
        "DEPLOY_HEALTH_CHECK",
        "deployment",
    ),
    # Alert channel
    _rule("POST", r"/alert-channels", "ALERT_CHANNEL_CREATE", "alert_channel"),
    _rule(
        "PATCH",
        r"/alert-channels/(?P<id>\d+)",
        "ALERT_CHANNEL_UPDATE",
        "alert_channel",
    ),
    _rule(
        "DELETE",
        r"/alert-channels/(?P<id>\d+)",
        "ALERT_CHANNEL_DELETE",
        "alert_channel",
    ),
    _rule(
        "POST",
        r"/alert-channels/(?P<id>\d+)/test",
        "ALERT_CHANNEL_TEST",
        "alert_channel",
    ),
    # Webhook GitHub (deployment otomatis dari push event)
    _rule("POST", r"/webhooks/github", "WEBHOOK_GITHUB", "webhook"),
)


def match_audit_rule(
    method: str, path: str
) -> tuple[AuditRule, dict[str, str]] | None:
    """Cocokkan request dengan allowlist audit.

    Returns:
        ``(rule, groups)`` bila cocok, ``None`` bila request tidak diaudit.
        ``groups`` adalah named regex groups dari path (mis. project_id, id).
    """
    for rule in AUDIT_RULES:
        if rule.method != method.upper():
            continue
        match = rule.pattern.match(path)
        if match is None:
            continue
        groups = {key: value for key, value in match.groupdict().items() if value}
        return rule, groups
    return None


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    return request.client.host if request.client else None


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        try:
            self._record(request, response.status_code)
        except Exception as exc:  # pragma: no cover - jalur defensif
            logger.warning(f"Audit middleware gagal memproses request: {exc}")

        return response

    @staticmethod
    def _record(request: Request, status_code: int) -> None:
        matched = match_audit_rule(request.method, request.url.path)
        if matched is None:
            return

        rule, groups = matched
        resource_id = groups.pop("id", None)

        state = request.state
        user = getattr(state, "current_user", None)
        username = getattr(user, "username", None) or getattr(
            state, "audit_username", None
        )
        user_id = getattr(user, "id", None) or getattr(state, "audit_user_id", None)

        user_agent = request.headers.get("user-agent")

        audit_service.record(
            audit_service.AuditEvent(
                action=rule.action,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                user_id=user_id,
                username=username,
                resource_type=rule.resource_type,
                resource_id=resource_id,
                ip_address=_client_ip(request),
                user_agent=user_agent[:255] if user_agent else None,
                details=groups,
            )
        )
