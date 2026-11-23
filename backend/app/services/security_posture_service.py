"""Agregasi posture keamanan dari image scan, TLS, dan konfigurasi container."""

from __future__ import annotations

import enum
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.image_scan import ImageScan, ImageScanStatus
from app.models.tls_domain import TlsDomain, TlsDomainStatus
from app.schemas.security_posture import (
    ContainerPostureSummary,
    ImagePostureSummary,
    PostureCheck,
    PostureFinding,
    SecurityPostureSummary,
    TlsPostureSummary,
)
from app.services import container_service

_SEVERITY_ORDER = {"critical": 0, "high": 1, "warning": 2, "info": 3}
_MAX_FINDINGS = 20


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _enum_value(value: object) -> str:
    return value.value if isinstance(value, enum.Enum) else str(value)


def _container_name(attrs: dict[str, Any]) -> str:
    raw_name = attrs.get("Name")
    if isinstance(raw_name, str) and raw_name.strip("/"):
        return raw_name.strip("/")
    config = _as_dict(attrs.get("Config"))
    image = config.get("Image")
    return str(image) if image else "container"


def _is_running(attrs: dict[str, Any]) -> bool:
    return _as_dict(attrs.get("State")).get("Status") == "running"


def _is_root_user(attrs: dict[str, Any]) -> bool:
    user = str(_as_dict(attrs.get("Config")).get("User") or "").strip().lower()
    return (
        not user
        or user == "root"
        or user == "0"
        or user.startswith("root:")
        or user.startswith("0:")
    )


def _has_writable_rootfs(attrs: dict[str, Any]) -> bool:
    return _as_dict(attrs.get("HostConfig")).get("ReadonlyRootfs") is not True


def _missing_cap_drop_all(attrs: dict[str, Any]) -> bool:
    cap_drop = _as_dict(attrs.get("HostConfig")).get("CapDrop") or []
    if not isinstance(cap_drop, list):
        cap_drop = [cap_drop]
    return not any(str(item).upper() == "ALL" for item in cap_drop)


def _missing_no_new_privileges(attrs: dict[str, Any]) -> bool:
    security_opt = _as_dict(attrs.get("HostConfig")).get("SecurityOpt") or []
    if not isinstance(security_opt, list):
        security_opt = [security_opt]
    return not any(
        str(item).lower().startswith("no-new-privileges") for item in security_opt
    )


def _load_container_attrs() -> tuple[list[dict[str, Any]], str | None]:
    try:
        client = container_service._get_client()
        containers = client.containers.list(all=True)
    except (ImportError, RuntimeError) as exc:
        return [], str(exc)
    except Exception as exc:  # pragma: no cover - jalur defensif Docker
        return [], f"Gagal membaca konfigurasi container: {exc}"
    return [container_service._safe_attrs(container) for container in containers], None


def _image_summary(scans: Sequence[ImageScan]) -> ImagePostureSummary:
    latest = max(
        (scan.scanned_at for scan in scans if scan.scanned_at is not None),
        default=None,
    )
    affected = {
        scan.image_name
        for scan in scans
        if (scan.critical_count or 0) > 0 or (scan.high_count or 0) > 0
    }
    return ImagePostureSummary(
        total_scans=len(scans),
        completed=sum(
            1 for scan in scans if _enum_value(scan.status) == ImageScanStatus.completed.value
        ),
        failed=sum(
            1 for scan in scans if _enum_value(scan.status) == ImageScanStatus.failed.value
        ),
        critical_count=sum(scan.critical_count or 0 for scan in scans),
        high_count=sum(scan.high_count or 0 for scan in scans),
        medium_count=sum(scan.medium_count or 0 for scan in scans),
        low_count=sum(scan.low_count or 0 for scan in scans),
        affected_images=len(affected),
        latest_scanned_at=latest,
    )


def _tls_summary(domains: Sequence[TlsDomain]) -> TlsPostureSummary:
    counts = {status: 0 for status in TlsDomainStatus}
    for domain in domains:
        counts[TlsDomainStatus(_enum_value(domain.status))] += 1
    return TlsPostureSummary(
        total=len(domains),
        enabled=sum(1 for domain in domains if domain.enabled),
        healthy=counts[TlsDomainStatus.healthy],
        expiring=counts[TlsDomainStatus.expiring],
        expired=counts[TlsDomainStatus.expired],
        invalid=counts[TlsDomainStatus.invalid],
        error=counts[TlsDomainStatus.error],
        pending=counts[TlsDomainStatus.pending],
    )


def _container_summary(
    attrs_list: Sequence[dict[str, Any]], error: str | None
) -> ContainerPostureSummary:
    running = [attrs for attrs in attrs_list if _is_running(attrs)]
    return ContainerPostureSummary(
        available=error is None,
        total=len(attrs_list),
        running=len(running),
        privileged=sum(
            1
            for attrs in running
            if bool(_as_dict(attrs.get("HostConfig")).get("Privileged"))
        ),
        root_user=sum(1 for attrs in running if _is_root_user(attrs)),
        writable_rootfs=sum(1 for attrs in running if _has_writable_rootfs(attrs)),
        missing_cap_drop_all=sum(1 for attrs in running if _missing_cap_drop_all(attrs)),
        missing_no_new_privileges=sum(
            1 for attrs in running if _missing_no_new_privileges(attrs)
        ),
        error_message=error,
    )


def _check(
    *,
    key: str,
    category: str,
    title: str,
    status: str,
    severity: str,
    detail: str,
    count: int = 0,
) -> PostureCheck:
    return PostureCheck(
        key=key,
        category=category,  # type: ignore[arg-type]
        title=title,
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        detail=detail,
        count=count,
    )


def _checks(
    images: ImagePostureSummary,
    tls: TlsPostureSummary,
    containers: ContainerPostureSummary,
) -> list[PostureCheck]:
    invalid_or_error = tls.invalid + tls.error
    docker_detail = (
        "Docker daemon dapat diakses."
        if containers.available
        else containers.error_message or "Docker daemon tidak tersedia."
    )
    return [
        _check(
            key="image_critical",
            category="image",
            title="Temuan CVE critical",
            status="fail" if images.critical_count else "pass",
            severity="critical",
            detail=(
                f"{images.critical_count} temuan critical pada image."
                if images.critical_count
                else "Tidak ada temuan critical pada riwayat scan."
            ),
            count=images.critical_count,
        ),
        _check(
            key="image_high",
            category="image",
            title="Temuan CVE high",
            status="warn" if images.high_count else "pass",
            severity="high",
            detail=(
                f"{images.high_count} temuan high pada image."
                if images.high_count
                else "Tidak ada temuan high pada riwayat scan."
            ),
            count=images.high_count,
        ),
        _check(
            key="image_failed_scan",
            category="image",
            title="Scan gagal",
            status="warn" if images.failed else "pass",
            severity="warning",
            detail=(
                f"{images.failed} pemindaian gagal dan perlu ditinjau."
                if images.failed
                else "Semua pemindaian selesai tanpa kegagalan."
            ),
            count=images.failed,
        ),
        _check(
            key="tls_expired",
            category="tls",
            title="Sertifikat kedaluwarsa",
            status="fail" if tls.expired else "pass",
            severity="critical",
            detail=(
                f"{tls.expired} sertifikat sudah kedaluwarsa."
                if tls.expired
                else "Tidak ada sertifikat kedaluwarsa."
            ),
            count=tls.expired,
        ),
        _check(
            key="tls_invalid_error",
            category="tls",
            title="Sertifikat invalid/error",
            status="fail" if invalid_or_error else "pass",
            severity="critical",
            detail=(
                f"{invalid_or_error} sertifikat invalid atau gagal diperiksa."
                if invalid_or_error
                else "Tidak ada sertifikat invalid atau error."
            ),
            count=invalid_or_error,
        ),
        _check(
            key="tls_expiring",
            category="tls",
            title="Sertifikat segera kedaluwarsa",
            status="warn" if tls.expiring else "pass",
            severity="warning",
            detail=(
                f"{tls.expiring} sertifikat mendekati kedaluwarsa."
                if tls.expiring
                else "Tidak ada sertifikat yang mendekati kedaluwarsa."
            ),
            count=tls.expiring,
        ),
        _check(
            key="tls_pending",
            category="tls",
            title="Pemeriksaan TLS tertunda",
            status="warn" if tls.pending else "pass",
            severity="info",
            detail=(
                f"{tls.pending} target TLS belum memiliki hasil pemeriksaan."
                if tls.pending
                else "Semua target TLS sudah diperiksa."
            ),
            count=tls.pending,
        ),
        _check(
            key="container_available",
            category="container",
            title="Docker daemon",
            status="unknown" if not containers.available else "pass",
            severity="warning",
            detail=docker_detail,
            count=0 if containers.available else 1,
        ),
        _check(
            key="container_privileged",
            category="container",
            title="Container privileged",
            status="fail" if containers.privileged else "pass",
            severity="critical",
            detail=(
                f"{containers.privileged} container berjalan dengan privileged mode."
                if containers.privileged
                else "Tidak ada container privileged yang berjalan."
            ),
            count=containers.privileged,
        ),
        _check(
            key="container_root_user",
            category="container",
            title="Container berjalan sebagai root",
            status="warn" if containers.root_user else "pass",
            severity="high",
            detail=(
                f"{containers.root_user} container memakai user root/default."
                if containers.root_user
                else "Tidak ada container yang terdeteksi berjalan sebagai root."
            ),
            count=containers.root_user,
        ),
        _check(
            key="container_readonly_rootfs",
            category="container",
            title="Root filesystem writable",
            status="warn" if containers.writable_rootfs else "pass",
            severity="warning",
            detail=(
                f"{containers.writable_rootfs} container tidak memakai read-only rootfs."
                if containers.writable_rootfs
                else "Semua container memakai read-only rootfs."
            ),
            count=containers.writable_rootfs,
        ),
        _check(
            key="container_cap_drop_all",
            category="container",
            title="Capability drop ALL",
            status="warn" if containers.missing_cap_drop_all else "pass",
            severity="warning",
            detail=(
                f"{containers.missing_cap_drop_all} container tidak menjatuhkan semua capability."
                if containers.missing_cap_drop_all
                else "Semua container menjatuhkan capability ALL."
            ),
            count=containers.missing_cap_drop_all,
        ),
        _check(
            key="container_no_new_privileges",
            category="container",
            title="No-new-privileges",
            status="warn" if containers.missing_no_new_privileges else "pass",
            severity="warning",
            detail=(
                f"{containers.missing_no_new_privileges} container tanpa opsi no-new-privileges."
                if containers.missing_no_new_privileges
                else "Semua container memakai no-new-privileges."
            ),
            count=containers.missing_no_new_privileges,
        ),
    ]


def _image_findings(scans: Sequence[ImageScan]) -> list[PostureFinding]:
    findings: list[PostureFinding] = []
    for scan in scans:
        if not ((scan.critical_count or 0) > 0 or (scan.high_count or 0) > 0):
            continue
        picked = 0
        raw_findings = scan.findings if isinstance(scan.findings, list) else []
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or "").lower()
            if severity not in {"critical", "high"}:
                continue
            cve_id = str(item.get("cve_id") or "CVE tanpa ID")
            package = str(item.get("package") or "package")
            findings.append(
                PostureFinding(
                    category="image",
                    severity="critical" if severity == "critical" else "high",
                    title=f"{cve_id} ({severity})",
                    detail=f"{package} pada image {scan.image_name}.",
                    resource=scan.image_name,
                )
            )
            picked += 1
            if picked >= 3:
                break
        if picked == 0:
            findings.append(
                PostureFinding(
                    category="image",
                    severity=(
                        "critical" if (scan.critical_count or 0) > 0 else "high"
                    ),
                    title="Temuan CVE pada image",
                    detail=(
                        f"{scan.critical_count or 0} critical dan "
                        f"{scan.high_count or 0} high pada {scan.image_name}."
                    ),
                    resource=scan.image_name,
                )
            )
    return findings


def _tls_findings(domains: Sequence[TlsDomain]) -> list[PostureFinding]:
    severity_by_status = {
        TlsDomainStatus.expired: "critical",
        TlsDomainStatus.invalid: "critical",
        TlsDomainStatus.error: "high",
        TlsDomainStatus.expiring: "warning",
    }
    findings: list[PostureFinding] = []
    for domain in domains:
        status = TlsDomainStatus(_enum_value(domain.status))
        severity = severity_by_status.get(status)
        if severity is None:
            continue
        detail = f"{domain.host}:{domain.port} berstatus {status.value}."
        if domain.error_message:
            detail = f"{detail} {domain.error_message}"
        findings.append(
            PostureFinding(
                category="tls",
                severity=severity,  # type: ignore[arg-type]
                title=f"TLS {status.value}",
                detail=detail,
                resource=f"{domain.host}:{domain.port}",
            )
        )
    return findings


def _container_findings(attrs_list: Sequence[dict[str, Any]]) -> list[PostureFinding]:
    findings: list[PostureFinding] = []
    for attrs in attrs_list:
        if not _is_running(attrs):
            continue
        name = _container_name(attrs)
        if bool(_as_dict(attrs.get("HostConfig")).get("Privileged")):
            findings.append(
                PostureFinding(
                    category="container",
                    severity="critical",
                    title="Container privileged",
                    detail=f"Container {name} berjalan dengan privileged mode.",
                    resource=name,
                )
            )
        if _is_root_user(attrs):
            findings.append(
                PostureFinding(
                    category="container",
                    severity="high",
                    title="User root",
                    detail=f"Container {name} berjalan sebagai root/default.",
                    resource=name,
                )
            )
        if _has_writable_rootfs(attrs):
            findings.append(
                PostureFinding(
                    category="container",
                    severity="warning",
                    title="Root filesystem writable",
                    detail=f"Container {name} tidak memakai read-only rootfs.",
                    resource=name,
                )
            )
        if _missing_cap_drop_all(attrs):
            findings.append(
                PostureFinding(
                    category="container",
                    severity="warning",
                    title="Capability tidak dibatasi",
                    detail=f"Container {name} tidak menjatuhkan capability ALL.",
                    resource=name,
                )
            )
        if _missing_no_new_privileges(attrs):
            findings.append(
                PostureFinding(
                    category="container",
                    severity="warning",
                    title="No-new-privileges tidak aktif",
                    detail=f"Container {name} tidak memakai opsi no-new-privileges.",
                    resource=name,
                )
            )
    return findings


def _score(
    images: ImagePostureSummary,
    tls: TlsPostureSummary,
    containers: ContainerPostureSummary,
) -> tuple[int, str]:
    image_penalty = min(
        40,
        images.critical_count * 4 + images.high_count + images.failed * 2,
    )
    tls_penalty = min(
        35,
        tls.expired * 15
        + tls.invalid * 10
        + tls.error * 8
        + tls.expiring * 3
        + tls.pending,
    )
    container_penalty = min(
        35,
        containers.privileged * 20
        + containers.root_user * 8
        + containers.writable_rootfs * 4
        + containers.missing_cap_drop_all * 3
        + containers.missing_no_new_privileges * 2,
    )
    value = max(0, 100 - image_penalty - tls_penalty - container_penalty)
    if value >= 80:
        level = "aman"
    elif value >= 50:
        level = "perlu_perhatian"
    else:
        level = "berisiko"
    return value, level


def _build_posture(
    scans: Sequence[ImageScan],
    domains: Sequence[TlsDomain],
    attrs_list: Sequence[dict[str, Any]],
    container_error: str | None,
) -> SecurityPostureSummary:
    images = _image_summary(scans)
    tls = _tls_summary(domains)
    containers = _container_summary(attrs_list, container_error)
    score, level = _score(images, tls, containers)

    findings = [
        *_image_findings(scans),
        *_tls_findings(domains),
        *_container_findings(attrs_list),
    ]
    findings.sort(key=lambda item: _SEVERITY_ORDER.get(item.severity, 99))

    return SecurityPostureSummary(
        score=score,
        level=level,  # type: ignore[arg-type]
        generated_at=datetime.now(tz=UTC),
        images=images,
        tls=tls,
        containers=containers,
        checks=_checks(images, tls, containers),
        findings=findings[:_MAX_FINDINGS],
    )


def build_posture(db: Session) -> SecurityPostureSummary:
    scans = list(db.query(ImageScan).all())
    domains = list(db.query(TlsDomain).all())
    attrs_list, container_error = _load_container_attrs()
    return _build_posture(scans, domains, attrs_list, container_error)
