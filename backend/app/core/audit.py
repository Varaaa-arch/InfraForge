from loguru import logger


def log_audit(action: str, *, user: str | None = None, **details: object) -> None:
    """
    Catat satu aksi bisnis penting , misal log_audit("LOGIN", user=user.username).

    Dipakai buat event yang perlu ketahuan siapa-ngapain, terpisah dari log request
    HTTP biasa yang dicatat otomatis lewat RequestLoggingMiddleware.
    """
    context = " ".join(f"{k}={v}" for k, v in details.items())
    who = f"user={user}" if user else ""
    logger.info(f"[{action}] {who}{context}".strip())
