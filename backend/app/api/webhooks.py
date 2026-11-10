"""
Router untuk GitHub Webhook Handler (Milestone 3 — P0).

Endpoint:
    POST /webhooks/github

Alur:
  1. Validasi signature HMAC SHA-256 dari header X-Hub-Signature-256.
  2. Parse payload push event.
  3. Filter: hanya proses event 'push' (header X-GitHub-Event).
  4. Extract branch dari ref.
  5. Cek idempotency via X-GitHub-Delivery.
  6. Cari aplikasi yang repository-nya match.
  7. Untuk setiap aplikasi yang match:
     a. Buat Deployment record (status=pending).
     b. Daftarkan background task via FastAPI BackgroundTasks.
  8. Return 202 Accepted — GitHub tidak perlu menunggu deployment selesai.

Keamanan:
  - Signature diverifikasi dari raw body (sebelum JSON parse).
  - Jika secret tidak dikonfigurasi → 500 (fail-closed).
  - Signature invalid → 401.
  - Event bukan 'push' → 200 (bukan error — GitHub retry kalau 4xx/5xx).
  - Delivery ID dedup → 200 (sudah diproses sebelumnya).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from loguru import logger

from app.config import settings
from app.core.audit import log_audit
from app.database.session import SessionLocal
from app.schemas.webhook import WebhookResponse
from app.services import deployment_queue, webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/github",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="GitHub Webhook Handler",
    description=(
        "Menerima webhook push event dari GitHub. "
        "Validasi signature HMAC SHA-256, lalu jalankan deployment di background. "
        "Mengembalikan 202 Accepted segera — deployment berjalan asynchronously."
    ),
    responses={
        202: {"description": "Webhook diterima, deployment di-schedule ke background"},
        401: {"description": "Signature tidak valid"},
        500: {"description": "Webhook secret tidak dikonfigurasi atau internal error"},
    },
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> WebhookResponse:
    # --- 0. Dapatkan raw body sebelum parsing ---
    raw_body = await request.body()

    # --- 1. Validasi signature ---
    if not settings.GITHUB_WEBHOOK_SECRET:
        logger.error("GITHUB_WEBHOOK_SECRET tidak dikonfigurasi — webhook ditolak.")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Webhook secret tidak dikonfigurasi",
        )

    if not webhook_service.verify_signature(raw_body, x_hub_signature_256):
        logger.warning("Webhook signature tidak valid.")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature tidak valid")

    # --- 2. Filter: hanya proses event 'push' ---
    if x_github_event != "push":
        logger.info(f"Webhook event '{x_github_event}' diabaikan (hanya 'push' yang diproses).")
        return WebhookResponse(
            accepted=False,
            message=f"Event '{x_github_event}' tidak diproses",
        )

    # --- 3. Parse payload ---
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("Webhook payload bukan JSON valid.")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payload bukan JSON valid")

    ref = payload.get("ref", "")
    branch = webhook_service.extract_branch(ref)

    if branch is None:
        logger.info(f"Webhook ref '{ref}' bukan branch push (mungkin tag) — diabaikan.")
        return WebhookResponse(accepted=False, message=f"Ref '{ref}' bukan branch push")

    # --- 4. Idempotency: cek delivery ID ---
    delivery_id = x_github_delivery or ""
    existing_deployment_id = deployment_queue.is_duplicate_delivery(delivery_id)
    if existing_deployment_id is not None:
        logger.info(
            f"Webhook delivery {delivery_id} sudah pernah diproses "
            f"(deployment #{existing_deployment_id})."
        )
        return WebhookResponse(
            accepted=False,
            message=f"Delivery {delivery_id} sudah pernah diproses",
            deployment_id=existing_deployment_id,
        )

    # --- 5. Cari aplikasi yang match ---
    repo_data = payload.get("repository", {})
    repo_url = ""
    if repo_data:
        repo_url = repo_data.get("html_url") or repo_data.get("clone_url") or ""

    with SessionLocal() as db:
        matching_apps = webhook_service.find_matching_applications(db, repo_url, branch)

        if not matching_apps:
            logger.info(
                f"Tidak ada aplikasi yang match untuk repo={repo_url} branch={branch}."
            )
            return WebhookResponse(
                accepted=False,
                message=f"Tidak ada aplikasi yang match untuk {repo_url} branch={branch}",
            )

        # --- 6. Untuk setiap aplikasi yang match: buat record + daftarkan background task ---
        from app.repositories import server_repository
        from app.services import deployment_service, project_service

        deployment_ids: list[int] = []
        skipped_locked: list[int] = []  # app_id yang sedang deploying

        for app in matching_apps:
            try:
                # --- Concurrency guard: skip jika app sedang deploying ---
                if deployment_queue.is_deployment_running(app.id):
                    running_id = deployment_queue.get_running_deployment_id(app.id)
                    logger.warning(
                        f"Webhook: app {app.id} sedang deploying "
                        f"(deployment_id={running_id}) — webhook push di-skip."
                    )
                    skipped_locked.append(app.id)
                    continue

                project = project_service.get_project_by_id(db, app.project_id)
                if project is None:
                    logger.warning(f"Project {app.project_id} tidak ditemukan untuk app {app.id}.")
                    continue

                servers = server_repository.list_by_owner(db, project.owner_id)
                if not servers:
                    logger.warning(f"Tidak ada server untuk project {app.project_id} (app {app.id}).")
                    continue

                server_id = servers[0].id

                # Buat Deployment record (sync, langsung commit ke DB)
                deployment, _app_obj, _server_obj = deployment_service.create_deployment_record(
                    db, app.id, server_id, branch_override=branch
                )

                # Mark delivery sebagai processed (idempotency)
                deployment_queue.mark_delivery_processed(delivery_id, deployment.id)

                # Daftarkan background task — akan dijalankan setelah response dikirim
                background_tasks.add_task(
                    deployment_queue.run_deployment_background,
                    deployment_id=deployment.id,
                    application_id=app.id,
                    server_id=server_id,
                )

                deployment_ids.append(deployment.id)
                logger.info(
                    f"Webhook → deployment #{deployment.id} scheduled "
                    f"(app={app.id}, branch={branch})"
                )

            except ValueError as exc:
                logger.warning(f"Gagal membuat deployment untuk app {app.id}: {exc}")
                continue

        # --- 7. Return 202 Accepted ---
        if not deployment_ids:
            # Semua aplikasi sedang deploying atau tidak ada yang bisa di-schedule
            if skipped_locked:
                return WebhookResponse(
                    accepted=False,
                    message=(
                        f"Semua aplikasi yang match sedang deploying "
                        f"(app_ids={skipped_locked}). Push ini di-skip."
                    ),
                )
            return WebhookResponse(
                accepted=False,
                message="Tidak ada deployment yang berhasil di-schedule",
            )

        log_audit(
            "WEBHOOK_DEPLOYMENT",
            user=None,
            delivery_id=delivery_id,
            repo=repo_url,
            branch=branch,
            deployment_ids=deployment_ids,
        )

        return WebhookResponse(
            accepted=True,
            message=f"{len(deployment_ids)} deployment(s) scheduled",
            deployment_id=deployment_ids[0],
        )
