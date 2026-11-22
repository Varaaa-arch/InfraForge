#!/usr/bin/env python
"""Seed deterministik untuk skenario Playwright Milestone 7.

Jalankan di dalam container backend agar file log live dapat dibaca WebSocket:

    docker compose exec -T backend uv run --no-dev python scripts/seed_m7_e2e.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.roles import Role
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.application import AppStatus, Application
from app.models.deployment import Deployment, DeploymentStatus, TriggerSource
from app.models.project import GitProvider, Project, Visibility
from app.models.server import AuthType, Server, ServerStatus
from app.models.user import User

USERNAME = "e2e_m7"
PASSWORD = "e2e-password"
PROJECT_SLUG = "e2e-milestone-7"
LOG_PATH = "/tmp/infraforge-e2e-live.log"


def _reset(db) -> None:
    existing = db.query(User).filter(User.username == USERNAME).first()
    if existing is not None:
        db.delete(existing)
        db.commit()


def _append_log(text: str) -> None:
    with Path(LOG_PATH).open("a", encoding="utf-8") as handle:
        handle.write(f"{text}\n")


def _finish_log(deployment_id: int) -> None:
    db = SessionLocal()
    try:
        deployment = (
            db.query(Deployment)
            .filter(Deployment.id == deployment_id)
            .one_or_none()
        )
        if deployment is None:
            raise SystemExit(f"Deployment {deployment_id} tidak ditemukan")
        deployment.status = DeploymentStatus.success
        deployment.finished_at = datetime.now(timezone.utc)
        db.add(deployment)
        db.commit()
        print("ok")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--append-log")
    parser.add_argument("--finish-log", type=int)
    args = parser.parse_args()

    if args.append_log:
        _append_log(args.append_log)
        return
    if args.finish_log:
        _finish_log(args.finish_log)
        return

    db = SessionLocal()
    try:
        _reset(db)
        now = datetime.now(timezone.utc)

        user = User(
            username=USERNAME,
            email=f"{USERNAME}@example.com",
            password=hash_password(PASSWORD),
            full_name="E2E Milestone 7",
            role=Role.ADMIN.value,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            owner_id=user.id,
            name="E2E Milestone 7",
            slug=PROJECT_SLUG,
            description="Project deterministik untuk Playwright.",
            visibility=Visibility.private,
            repository_url="https://github.com/acme/infraforge-e2e",
            default_branch="main",
            provider=GitProvider.github,
            repository_connected_at=now,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        server = Server(
            owner_id=user.id,
            name="E2E Server",
            host="192.0.2.77",
            port=22,
            username="deploy",
            auth_type=AuthType.password,
            password="e2e-secret",
            status=ServerStatus.active,
        )
        db.add(server)
        db.commit()
        db.refresh(server)

        api = Application(
            project_id=project.id,
            name="api",
            repository=project.repository_url,
            branch="main",
            compose_path="docker-compose.yml",
            status=AppStatus.running,
            webhook_branches=["main"],
        )
        worker = Application(
            project_id=project.id,
            name="worker",
            repository=project.repository_url,
            branch="main",
            compose_path="docker-compose.yml",
            status=AppStatus.idle,
            webhook_branches=["main"],
        )
        log_worker = Application(
            project_id=project.id,
            name="log-worker",
            repository=project.repository_url,
            branch="main",
            compose_path="docker-compose.yml",
            status=AppStatus.idle,
            webhook_branches=["main"],
        )
        db.add_all([api, worker, log_worker])
        db.commit()
        for application in (api, worker, log_worker):
            db.refresh(application)

        old_success = Deployment(
            application_id=api.id,
            server_id=server.id,
            status=DeploymentStatus.success,
            branch="main",
            trigger_source=TriggerSource.manual.value,
            commit_sha="1111111111111111111111111111111111111111",
            tag="v1.0.0",
            triggered_by="e2e-seed",
            compose_path_snapshot="docker-compose.yml",
            started_at=now - timedelta(hours=3),
            finished_at=now - timedelta(hours=3) + timedelta(minutes=2),
        )
        latest_success = Deployment(
            application_id=api.id,
            server_id=server.id,
            status=DeploymentStatus.success,
            branch="main",
            trigger_source=TriggerSource.manual.value,
            commit_sha="2222222222222222222222222222222222222222",
            tag="v1.1.0",
            triggered_by="e2e-seed",
            compose_path_snapshot="docker-compose.yml",
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1) + timedelta(minutes=2),
        )
        log_file = Path(LOG_PATH)
        log_file.write_text(
            "[InfraForge] E2E live deployment\n"
            "Cloning repository...\n"
            "docker compose build dimulai\n",
            encoding="utf-8",
        )
        live = Deployment(
            application_id=log_worker.id,
            server_id=server.id,
            status=DeploymentStatus.deploying,
            branch="main",
            trigger_source=TriggerSource.manual.value,
            commit_sha="3333333333333333333333333333333333333333",
            triggered_by="e2e-seed",
            log_path=LOG_PATH,
            started_at=now,
        )
        db.add_all([old_success, latest_success, live])
        db.commit()
        for deployment in (old_success, latest_success, live):
            db.refresh(deployment)

        print(
            json.dumps(
                {
                    "username": USERNAME,
                    "password": PASSWORD,
                    "project_id": project.id,
                    "api_application_id": api.id,
                    "worker_application_id": worker.id,
                    "log_worker_application_id": log_worker.id,
                    "old_success_deployment_id": old_success.id,
                    "latest_success_deployment_id": latest_success.id,
                    "live_deployment_id": live.id,
                    "log_path": LOG_PATH,
                }
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
