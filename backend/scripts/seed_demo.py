#!/usr/bin/env python
"""Seed data demo idempotent untuk InfraForge.

Jalankan terhadap database yang dipakai aplikasi Docker:

    docker compose exec backend uv run --no-dev python scripts/seed_demo.py

Script selalu menghapus lalu membuat ulang data milik user `demo`, sehingga
aman dijalankan berkali-kali tanpa membuat duplikat:

- user `demo` / `demo1234`
- 1 project, 2 server, 2 aplikasi, 4 deployment
- 2 environment variable terenkripsi
- 24 riwayat alert (7 rule bawaan, campuran firing/resolved)
- 1 channel notifikasi dummy berstatus nonaktif
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.alert import (
    AlertChannel,
    AlertChannelType,
    AlertEvent,
    AlertStatus,
)
from app.models.application import AppStatus, Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.env_var import EnvVar
from app.models.project import GitProvider, Project, Visibility
from app.models.server import AuthType, Server, ServerStatus
from app.models.user import User
from app.services import encryption_service

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo1234"
DEMO_EMAIL = "demo@example.com"
DEMO_FULL_NAME = "Demo User"
DEMO_PROJECT_SLUG = "demo-project"
DEMO_CHANNEL_NAME = "Demo Discord (nonaktif)"
DEMO_FINGERPRINT_PREFIX = "demo-"

RULE_SAMPLES = [
    (
        "HighHostCPUUsage",
        "critical",
        "node-exporter",
        "CPU host di atas 90% selama 5 menit",
        "Penggunaan CPU host {instance} mencapai {value}%. Periksa proses yang boros CPU.",
        "94.2%",
    ),
    (
        "HighHostMemoryUsage",
        "critical",
        "node-exporter",
        "RAM host di atas 90% selama 5 menit",
        "Pemakaian memori host {instance} mencapai {value}%. Pertimbangkan menambah RAM atau membunuh proses.",
        "91.7%",
    ),
    (
        "HighDiskUsage",
        "warning",
        "node-exporter",
        "Disk host di atas 90%",
        "Partisi / pada {instance} terpakai {value}%. Bersihkan log atau tambah kapasitas.",
        "92.4%",
    ),
    (
        "InfraContainerDown",
        "critical",
        "backend",
        "Container compose infraforge mati lebih dari 2 menit",
        "Container {value} di project compose infraforge tidak berjalan. Cek `docker compose ps`.",
        "infraforge-loki",
    ),
    (
        "ContainerRestartLoop",
        "warning",
        "backend",
        "Container restart lebih dari 2 kali dalam 15 menit",
        "Container {value} restart berulang kali. Periksa log container untuk mencari penyebab crash.",
        "infraforge-backend",
    ),
    (
        "DockerDaemonUnavailable",
        "critical",
        "backend",
        "Docker daemon tidak terdeteksi",
        "Exporter backend tidak dapat menghubungi Docker daemon di {instance}. Deployment dan metrik container berhenti.",
        "docker.sock",
    ),
    (
        "MonitoringTargetDown",
        "warning",
        "prometheus",
        "Target scrape Prometheus down",
        "Target {instance} tidak dapat di-scrape oleh Prometheus. Periksa service dan jaringan.",
        "node-exporter:9100",
    ),
]

DEMO_ENV_VARS = [
    ("DEMO_API_KEY", "sk-demo-1234567890abcdef"),
    ("LOG_LEVEL", "info"),
]


def _log(message: str) -> None:
    print(message)


def _delete_demo_data(db: Session) -> None:
    user = db.query(User).filter(User.username == DEMO_USERNAME).one_or_none()
    if user is not None:
        project_ids = [
            project.id
            for project in db.query(Project).filter(Project.owner_id == user.id).all()
        ]
        application_ids = []
        if project_ids:
            application_ids = [
                app.id
                for app in db.query(Application)
                .filter(Application.project_id.in_(project_ids))
                .all()
            ]
        if application_ids:
            db.query(Deployment).filter(
                Deployment.application_id.in_(application_ids)
            ).delete(synchronize_session=False)
        if project_ids:
            db.query(EnvVar).filter(EnvVar.project_id.in_(project_ids)).delete(
                synchronize_session=False
            )
            db.query(Application).filter(
                Application.project_id.in_(project_ids)
            ).delete(synchronize_session=False)
            db.query(Project).filter(Project.id.in_(project_ids)).delete(
                synchronize_session=False
            )
        db.query(Server).filter(Server.owner_id == user.id).delete(
            synchronize_session=False
        )
        db.delete(user)

    db.query(AlertEvent).filter(
        AlertEvent.fingerprint.like(f"{DEMO_FINGERPRINT_PREFIX}%")
    ).delete(synchronize_session=False)
    db.query(AlertChannel).filter(AlertChannel.name == DEMO_CHANNEL_NAME).delete(
        synchronize_session=False
    )
    db.commit()
    _log("Data demo lama dibersihkan.")


def _seed_user(db: Session) -> User:
    user = User(
        username=DEMO_USERNAME,
        email=DEMO_EMAIL,
        password=hash_password(DEMO_PASSWORD),
        full_name=DEMO_FULL_NAME,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_project(db: Session, owner_id: int) -> Project:
    project = Project(
        owner_id=owner_id,
        name="Demo Project",
        slug=DEMO_PROJECT_SLUG,
        description=(
            "Project contoh untuk mencoba dashboard InfraForge: server, aplikasi, "
            "deployment, environment variable, dan riwayat alert."
        ),
        visibility=Visibility.public,
        repository_url="https://github.com/Varaaa-arch/InfraForge",
        default_branch="main",
        provider=GitProvider.github,
        repository_connected_at=datetime.now(timezone.utc),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _seed_servers(db: Session, owner_id: int) -> list[Server]:
    servers = [
        Server(
            owner_id=owner_id,
            name="Demo Server 1",
            host="192.0.2.10",
            port=22,
            username="deploy",
            exporter_instance="host.docker.internal:9100",
            auth_type=AuthType.password,
            password="demo-password",
            status=ServerStatus.active,
        ),
        Server(
            owner_id=owner_id,
            name="Demo Server 2",
            host="192.0.2.11",
            port=22,
            username="deploy",
            auth_type=AuthType.password,
            password="demo-password",
            status=ServerStatus.inactive,
        ),
    ]
    db.add_all(servers)
    db.commit()
    for server in servers:
        db.refresh(server)
    return servers


def _seed_applications(db: Session, project_id: int) -> list[Application]:
    applications = [
        Application(
            project_id=project_id,
            name="demo-api",
            repository="https://github.com/Varaaa-arch/InfraForge",
            branch="main",
            dockerfile_path="backend/Dockerfile",
            compose_path="docker-compose.yml",
            status=AppStatus.running,
        ),
        Application(
            project_id=project_id,
            name="demo-web",
            repository="https://github.com/Varaaa-arch/InfraForge",
            branch="main",
            dockerfile_path="frontend/Dockerfile",
            compose_path="docker-compose.yml",
            status=AppStatus.idle,
        ),
    ]
    db.add_all(applications)
    db.commit()
    for application in applications:
        db.refresh(application)
    return applications


def _seed_deployments(
    db: Session, applications: list[Application], servers: list[Server]
) -> list[Deployment]:
    now = datetime.now(timezone.utc)
    api, web = applications
    active_server = servers[0]
    deployments = [
        Deployment(
            application_id=api.id,
            server_id=active_server.id,
            status=DeploymentStatus.success,
            branch="main",
            commit_sha="a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            log_path="/var/log/infraforge/demo/deploy-1.log",
            compose_path_snapshot="docker-compose.yml",
            started_at=now - timedelta(days=6, hours=2),
            finished_at=now - timedelta(days=6, hours=2) + timedelta(minutes=4),
        ),
        Deployment(
            application_id=api.id,
            server_id=active_server.id,
            status=DeploymentStatus.failed,
            branch="main",
            commit_sha="b2c3d4e5f60718293a4b5c6d7e8f901234567890",
            log_path="/var/log/infraforge/demo/deploy-2.log",
            started_at=now - timedelta(days=1, hours=3),
            finished_at=now - timedelta(days=1, hours=3) + timedelta(minutes=2),
        ),
        Deployment(
            application_id=api.id,
            server_id=active_server.id,
            status=DeploymentStatus.success,
            branch="main",
            commit_sha="c3d4e5f60718293a4b5c6d7e8f90123456789012",
            log_path="/var/log/infraforge/demo/deploy-3.log",
            rollback_of=None,
            compose_path_snapshot="docker-compose.yml",
            started_at=now - timedelta(hours=5),
            finished_at=now - timedelta(hours=5) + timedelta(minutes=3),
        ),
        Deployment(
            application_id=web.id,
            server_id=active_server.id,
            status=DeploymentStatus.success,
            branch="main",
            commit_sha="d4e5f60718293a4b5c6d7e8f9012345678901234",
            log_path="/var/log/infraforge/demo/deploy-4.log",
            compose_path_snapshot="docker-compose.yml",
            started_at=now - timedelta(days=2, hours=1),
            finished_at=now - timedelta(days=2, hours=1) + timedelta(minutes=5),
        ),
    ]
    db.add_all(deployments)
    db.commit()
    for deployment in deployments:
        db.refresh(deployment)
    return deployments


def _seed_env_vars(db: Session, project_id: int) -> list[EnvVar]:
    env_vars = [
        EnvVar(
            project_id=project_id,
            key=key,
            encrypted_value=encryption_service.encrypt(value),
        )
        for key, value in DEMO_ENV_VARS
    ]
    db.add_all(env_vars)
    db.commit()
    return env_vars


def _seed_alert_events(db: Session) -> list[AlertEvent]:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []
    for index in range(24):
        alert_name, severity, job, summary, description, value = RULE_SAMPLES[
            index % len(RULE_SAMPLES)
        ]
        status = AlertStatus.resolved if index % 3 != 0 else AlertStatus.firing
        starts_at = now - timedelta(hours=(index + 1) * 7)
        ends_at = (
            starts_at + timedelta(minutes=9 + index * 3)
            if status == AlertStatus.resolved
            else None
        )
        instance = "node-exporter:9100"
        if alert_name in {
            "InfraContainerDown",
            "ContainerRestartLoop",
            "DockerDaemonUnavailable",
        }:
            instance = "infraforge"
        events.append(
            AlertEvent(
                fingerprint=f"{DEMO_FINGERPRINT_PREFIX}{index + 1:03d}",
                alert_name=alert_name,
                status=status,
                severity=severity,
                summary=summary,
                description=description.format(instance=instance, value=value),
                labels={
                    "alertname": alert_name,
                    "severity": severity,
                    "job": job,
                    "instance": instance,
                },
                annotations={
                    "summary": summary,
                    "description": description.format(instance=instance, value=value),
                },
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )
    db.add_all(events)
    db.commit()
    return events


def _seed_alert_channel(db: Session) -> AlertChannel:
    channel = AlertChannel(
        name=DEMO_CHANNEL_NAME,
        channel_type=AlertChannelType.discord,
        encrypted_discord_webhook_url=encryption_service.encrypt(
            "https://discord.com/api/webhooks/000000000000000000/demo-placeholder"
        ),
        enabled=False,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _print_summary(db: Session) -> None:
    user = db.query(User).filter(User.username == DEMO_USERNAME).one()
    project_ids = [
        project.id
        for project in db.query(Project).filter(Project.owner_id == user.id).all()
    ]
    application_ids = [
        app.id
        for app in db.query(Application)
        .filter(Application.project_id.in_(project_ids))
        .all()
    ]
    counts = {
        "server": db.query(Server).filter(Server.owner_id == user.id).count(),
        "project": len(project_ids),
        "application": len(application_ids),
        "deployment": db.query(Deployment)
        .filter(Deployment.application_id.in_(application_ids))
        .count()
        if application_ids
        else 0,
        "env_var": db.query(EnvVar)
        .filter(EnvVar.project_id.in_(project_ids))
        .count()
        if project_ids
        else 0,
        "alert_event": db.query(AlertEvent)
        .filter(AlertEvent.fingerprint.like(f"{DEMO_FINGERPRINT_PREFIX}%"))
        .count(),
        "alert_channel": db.query(AlertChannel)
        .filter(AlertChannel.name == DEMO_CHANNEL_NAME)
        .count(),
    }
    _log("")
    _log("Data demo siap:")
    for name, count in counts.items():
        _log(f"  - {name}: {count}")
    _log("")
    _log(f"Login demo: {DEMO_USERNAME} / {DEMO_PASSWORD}")
    _log(f"Channel '{DEMO_CHANNEL_NAME}' sengaja nonaktif — ganti URL webhook asli sebelum diaktifkan.")


def main() -> None:
    db_url = settings.db_url
    for secret in (settings.POSTGRES_PASSWORD, settings.POSTGRES_USER):
        if secret:
            db_url = db_url.replace(secret, "***")
    _log(f"Target database: {db_url}")

    db = SessionLocal()
    try:
        _delete_demo_data(db)
        user = _seed_user(db)
        project = _seed_project(db, user.id)
        servers = _seed_servers(db, user.id)
        applications = _seed_applications(db, project.id)
        _seed_deployments(db, applications, servers)
        _seed_env_vars(db, project.id)
        _seed_alert_events(db)
        _seed_alert_channel(db)
        _print_summary(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
