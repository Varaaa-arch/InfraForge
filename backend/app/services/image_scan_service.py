"""Service pemindaian kerentanan image container menggunakan Trivy.

Pemindaian dijalankan sebagai subprocess tanpa shell agar referensi image tidak
bisa disisipi perintah. Kegagalan scanner (binary tidak ada, timeout, output
rusak) tidak menggagalkan request API: baris scan tetap tersimpan dengan status
``failed`` dan pesan error yang bisa ditampilkan ke pengguna.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.models.image_scan import ImageScan, ImageScanStatus
from app.repositories import alert_channel_repository, image_scan_repository
from app.services import alert_service

SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low")
_IMAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]*$")
_MAX_ERROR_LENGTH = 1000


class ScanError(RuntimeError):
    """Kegagalan yang bisa ditampilkan ke pengguna saat pemindaian."""


@dataclass(slots=True)
class TrivySummary:
    image_digest: str | None
    overall_severity: str
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_count: int
    findings: list[dict[str, Any]] = field(default_factory=list)


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _image_digest(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("Metadata")
    if not isinstance(metadata, dict):
        return None
    image_id = _string(metadata.get("ImageID"))
    if image_id:
        return image_id[:128]
    repo_digests = metadata.get("RepoDigests")
    if isinstance(repo_digests, list):
        for digest in repo_digests:
            text = _string(digest)
            if text:
                return text[:128]
    return None


def _overall_severity(counts: dict[str, int], total: int) -> str:
    for severity in SEVERITIES:
        if counts[severity] > 0:
            return severity
    return "none" if total == 0 else "unknown"


def parse_trivy_output(raw: str, *, max_findings: int = 500) -> TrivySummary:
    """Parse output ``trivy image --format json`` menjadi ringkasan ringkas."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScanError(f"Output Trivy bukan JSON yang valid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ScanError("Format output Trivy tidak dikenali")

    results = payload.get("Results", [])
    if results is None:
        results = []
    if not isinstance(results, list):
        raise ScanError("Format Results Trivy tidak dikenali")

    counts = {severity: 0 for severity in SEVERITIES}
    findings: list[dict[str, Any]] = []
    total = 0
    limit = max(0, max_findings)

    for result in results:
        if not isinstance(result, dict):
            continue
        target = _string(result.get("Target"))
        vulnerabilities = result.get("Vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            continue
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            total += 1
            raw_severity = (_string(vulnerability.get("Severity")) or "unknown").lower()
            severity = raw_severity if raw_severity in counts else "unknown"
            if severity in counts:
                counts[severity] += 1
            if len(findings) >= limit:
                continue
            findings.append(
                {
                    "cve_id": _string(vulnerability.get("VulnerabilityID"))
                    or "UNKNOWN",
                    "package": _string(vulnerability.get("PkgName")) or "unknown",
                    "installed_version": _string(
                        vulnerability.get("InstalledVersion")
                    ),
                    "fixed_version": _string(vulnerability.get("FixedVersion")),
                    "severity": severity,
                    "title": _string(vulnerability.get("Title")),
                    "target": target,
                    "primary_url": _string(vulnerability.get("PrimaryURL")),
                }
            )

    return TrivySummary(
        image_digest=_image_digest(payload),
        overall_severity=_overall_severity(counts, total),
        critical_count=counts["critical"],
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
        total_count=total,
        findings=findings,
    )


def _run_trivy(image_name: str) -> str:
    if not _IMAGE_NAME_RE.fullmatch(image_name):
        raise ScanError("Referensi image tidak valid")

    command = [
        settings.TRIVY_PATH,
        "image",
        "--format",
        "json",
        "--quiet",
        "--no-progress",
        "--scanners",
        "vuln",
        image_name,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.IMAGE_SCAN_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ScanError(
            "Trivy tidak tersedia di backend. Pasang binary Trivy atau set "
            "TRIVY_PATH ke lokasi binary."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ScanError(
            f"Pemindaian melebihi batas waktu "
            f"{settings.IMAGE_SCAN_TIMEOUT_SECONDS} detik"
        ) from exc
    except OSError as exc:
        raise ScanError(f"Gagal menjalankan Trivy: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        detail = detail[-500:] if detail else "tanpa detail"
        raise ScanError(f"Trivy keluar dengan kode {completed.returncode}: {detail}")

    stdout = completed.stdout or ""
    if len(stdout.encode("utf-8", errors="replace")) > settings.IMAGE_SCAN_MAX_OUTPUT_BYTES:
        raise ScanError(
            "Output Trivy melebihi batas ukuran "
            f"{settings.IMAGE_SCAN_MAX_OUTPUT_BYTES} byte"
        )
    return stdout


def _scan_sync(image_name: str) -> TrivySummary:
    return parse_trivy_output(
        _run_trivy(image_name),
        max_findings=settings.IMAGE_SCAN_MAX_FINDINGS,
    )


def create_scan(
    db: Session,
    *,
    image_name: str,
    project_id: int | None,
    requested_by: str | None,
) -> ImageScan:
    normalized = image_name.strip()
    if not _IMAGE_NAME_RE.fullmatch(normalized):
        raise ValueError("Referensi image tidak valid")
    return image_scan_repository.create(
        db,
        image_name=normalized,
        project_id=project_id,
        requested_by=requested_by,
    )


def create_rescan(db: Session, scan: ImageScan, *, requested_by: str | None) -> ImageScan:
    return image_scan_repository.create(
        db,
        image_name=scan.image_name,
        project_id=scan.project_id,
        requested_by=requested_by,
    )


def _mark_failed(scan: ImageScan, message: str) -> None:
    scan.status = ImageScanStatus.failed
    scan.error_message = message[:_MAX_ERROR_LENGTH]
    scan.scanned_at = datetime.now(timezone.utc)


async def execute_scan(db: Session, scan: ImageScan) -> ImageScan:
    """Jalankan Trivy tanpa memblokir event loop lalu simpan hasilnya."""
    scan.status = ImageScanStatus.running
    scan.error_message = None
    image_scan_repository.save(db, scan)

    try:
        summary = await asyncio.to_thread(_scan_sync, scan.image_name)
    except ScanError as exc:
        _mark_failed(scan, str(exc))
    except Exception as exc:  # pragma: no cover - jalur defensif
        logger.exception(f"Pemindaian image {scan.image_name} gagal tak terduga")
        _mark_failed(scan, f"Pemindaian gagal: {exc}")
    else:
        scan.status = ImageScanStatus.completed
        scan.image_digest = summary.image_digest
        scan.overall_severity = summary.overall_severity
        scan.critical_count = summary.critical_count
        scan.high_count = summary.high_count
        scan.medium_count = summary.medium_count
        scan.low_count = summary.low_count
        scan.total_count = summary.total_count
        scan.findings = summary.findings
        scan.error_message = None
        scan.scanned_at = datetime.now(timezone.utc)

    saved = image_scan_repository.save(db, scan)
    if saved.status == ImageScanStatus.completed:
        notify_vulnerability_threshold(db, saved)
    return saved


def notify_vulnerability_threshold(db: Session, scan: ImageScan) -> None:
    """Kirim notifikasi best-effort bila temuan melewati ambang batas."""
    if not settings.IMAGE_SCAN_NOTIFICATIONS_ENABLED:
        return

    critical_exceeded = scan.critical_count > settings.IMAGE_SCAN_CRITICAL_THRESHOLD
    high_exceeded = scan.high_count > settings.IMAGE_SCAN_HIGH_THRESHOLD
    if not critical_exceeded and not high_exceeded:
        return

    severity = "critical" if critical_exceeded else "warning"
    try:
        channels = alert_channel_repository.list_enabled_for_severity(db, severity)
        if not channels:
            return
        project_label = (
            f"project #{scan.project_id}" if scan.project_id is not None else "tanpa project"
        )
        event = alert_service.NotificationEvent(
            alert_name="ImageVulnerabilitiesDetected",
            status="event",
            severity=severity,
            summary=(
                f"Image {scan.image_name}: {scan.critical_count} critical, "
                f"{scan.high_count} high"
            ),
            description=(
                f"Pemindaian image {scan.image_name} ({project_label}) menemukan "
                f"{scan.critical_count} CRITICAL dan {scan.high_count} HIGH "
                f"kerentanan dari total {scan.total_count} temuan."
            ),
            labels={
                "event": "image_scan",
                "scan_id": str(scan.id),
                "image": scan.image_name,
                "severity": scan.overall_severity or "unknown",
                "critical": str(scan.critical_count),
                "high": str(scan.high_count),
            },
            annotations={},
            starts_at=scan.scanned_at or datetime.now(timezone.utc),
            ends_at=None,
        )
        for channel in channels:
            try:
                alert_service.send_to_channel(channel, event)
                logger.info(
                    f"Notifikasi kerentanan image {scan.image_name} dikirim "
                    f"ke channel {channel.name}."
                )
            except Exception as exc:
                logger.error(
                    f"Gagal mengirim notifikasi kerentanan image "
                    f"{scan.image_name} ke channel {channel.name}: {exc}"
                )
    except Exception as exc:
        logger.error(f"Gagal menyiapkan notifikasi kerentanan image: {exc}")
