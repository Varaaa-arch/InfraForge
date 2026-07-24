import time

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable, Awaitable

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        client_ip = request.client.host if request.client else "unknown"
        message = (
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"duration={duration_ms:.2f}ms "
            f"client={client_ip}"
        )

        if response.status_code >= 500:
            logger.error(message)
        elif response.status_code >= 400:
            logger.warning(message)
        else:
            logger.info(message)

        return response
