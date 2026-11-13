"""Router alerting: webhook Alertmanager, riwayat alert, dan channel notifikasi."""

from __future__ import annotations

import hmac

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    status,
)
from loguru import logger
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.alert import AlertStatus
from app.models.user import User
from app.schemas.alert import (
    AlertChannelCreate,
    AlertChannelResponse,
    AlertChannelUpdate,
    AlertEventResponse,
    AlertIngestResponse,
    AlertmanagerPayload,
)
from app.schemas.common import MessageResponse
from app.schemas.response import ApiResponse
from app.services import alert_channel_service, alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])
channels_router = APIRouter(prefix="/alert-channels", tags=["alerts"])


@router.post(
    "/webhook",
    response_model=ApiResponse[AlertIngestResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Webhook Alertmanager",
    description=(
        "Menerima payload webhook dari Alertmanager, menyimpan riwayat alert, "
        "dan mengirim notifikasi ke channel Discord/Telegram yang aktif."
    ),
)
def alertmanager_webhook(
    payload: AlertmanagerPayload,
    background_tasks: BackgroundTasks,
    token: str | None = Query(default=None),
    x_infraforge_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertIngestResponse]:
    if not settings.ALERT_WEBHOOK_SECRET:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ALERT_WEBHOOK_SECRET belum dikonfigurasi",
        )
    provided_token = x_infraforge_token or token
    if not provided_token or not hmac.compare_digest(
        provided_token, settings.ALERT_WEBHOOK_SECRET
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token webhook tidak valid")

    result = alert_service.ingest(db, payload)
    background_tasks.add_task(
        alert_service.dispatch_event_notifications, result.event_ids
    )
    logger.info(
        f"Alertmanager webhook: {result.received} alert diterima, "
        f"{result.created} firing baru, {result.resolved} resolved."
    )
    return ApiResponse(
        data=AlertIngestResponse(
            received=result.received,
            created=result.created,
            resolved=result.resolved,
        )
    )


@router.get(
    "",
    response_model=ApiResponse[list[AlertEventResponse]],
    summary="Riwayat alert",
    description="Daftar alert terbaru, bisa difilter berdasarkan status dan severity.",
)
def list_alerts(
    alert_status: AlertStatus | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[AlertEventResponse]]:
    events = alert_service.list_events(
        db,
        status=alert_status,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=[AlertEventResponse.model_validate(event) for event in events])


@channels_router.get(
    "",
    response_model=ApiResponse[list[AlertChannelResponse]],
    summary="List channel notifikasi",
)
def list_channels(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[AlertChannelResponse]]:
    channels = alert_channel_service.list_channels(db)
    return ApiResponse(data=[alert_channel_service.to_response(ch) for ch in channels])


@channels_router.post(
    "",
    response_model=ApiResponse[AlertChannelResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Tambah channel notifikasi",
)
def create_channel(
    payload: AlertChannelCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertChannelResponse]:
    channel = alert_channel_service.create_channel(db, payload)
    log_audit(
        "CREATE_ALERT_CHANNEL",
        user=current_user.username,
        channel_id=channel.id,
        channel_type=payload.type.value,
    )
    return ApiResponse(data=alert_channel_service.to_response(channel))


@channels_router.patch(
    "/{channel_id}",
    response_model=ApiResponse[AlertChannelResponse],
    summary="Update channel notifikasi",
)
def update_channel(
    channel_id: int,
    payload: AlertChannelUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AlertChannelResponse]:
    channel = alert_channel_service.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel tidak ditemukan")
    try:
        channel = alert_channel_service.update_channel(db, channel, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    log_audit(
        "UPDATE_ALERT_CHANNEL",
        user=current_user.username,
        channel_id=channel.id,
    )
    return ApiResponse(data=alert_channel_service.to_response(channel))


@channels_router.delete(
    "/{channel_id}",
    response_model=ApiResponse[MessageResponse],
    summary="Hapus channel notifikasi",
)
def delete_channel(
    channel_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    channel = alert_channel_service.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel tidak ditemukan")
    alert_channel_service.delete_channel(db, channel)
    log_audit(
        "DELETE_ALERT_CHANNEL",
        user=current_user.username,
        channel_id=channel_id,
    )
    return ApiResponse(data=MessageResponse(message="Channel deleted successfully"))


@channels_router.post(
    "/{channel_id}/test",
    response_model=ApiResponse[MessageResponse],
    summary="Kirim notifikasi uji",
)
def test_channel(
    channel_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    channel = alert_channel_service.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel tidak ditemukan")
    try:
        alert_service.send_test(channel)
    except Exception as exc:
        logger.warning(f"Test channel {channel.name} gagal: {exc}")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Gagal mengirim notifikasi uji. Periksa kembali konfigurasi channel.",
        )
    log_audit(
        "TEST_ALERT_CHANNEL",
        user=current_user.username,
        channel_id=channel_id,
    )
    return ApiResponse(data=MessageResponse(message="Notifikasi uji terkirim"))
