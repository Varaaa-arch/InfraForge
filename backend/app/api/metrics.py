"""Endpoint /metrics untuk scraping Prometheus."""

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.services import metrics_service

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    metrics_service.collect()
    return Response(
        content=generate_latest(metrics_service.REGISTRY),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
