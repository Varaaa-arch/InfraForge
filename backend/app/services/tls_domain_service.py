"""Inspeksi sertifikat TLS/SSL target domain dan pencatatan hasilnya.

Inspeksi memakai stdlib ``ssl``/``socket`` untuk koneksi dan ``cryptography``
untuk membaca detail DER sertifikat. Handshake pertama tidak memverifikasi
sertifikat agar detail tetap bisa ditampilkan walau sertifikat kedaluwarsa,
self-signed, atau hostname-nya tidak cocok. Verifikasi chain/hostname dilakukan
pada handshake kedua hanya bila metadata dasar sudah lolos.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography import x509
from cryptography.x509.oid import NameOID
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.models.tls_domain import TlsDomain, TlsDomainCheck, TlsDomainStatus
from app.repositories import alert_channel_repository, tls_domain_repository
from app.services import alert_service

_HOST_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, TlsInspection]] = {}
_MAX_CACHE_ENTRIES = 512
_WARNING_STATUSES = frozenset(
    {TlsDomainStatus.expiring, TlsDomainStatus.expired, TlsDomainStatus.invalid, TlsDomainStatus.error}
)


class TlsTargetError(ValueError):
    """Target tidak valid atau diblokir oleh kebijakan keamanan."""


@dataclass(slots=True)
class TlsInspection:
    status: TlsDomainStatus
    checked_at: datetime
    days_remaining: int | None = None
    expiry_date: datetime | None = None
    issuer: str | None = None
    subject: str | None = None
    protocol: str | None = None
    trusted: bool = False
    error_message: str | None = None


def normalize_host(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _is_non_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _resolves_to_non_public(host: str, port: int) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return _is_non_public(address)

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except (ValueError, IndexError):
            continue
    return bool(addresses) and any(_is_non_public(item) for item in addresses)


def validate_target(host: str, port: int) -> str:
    """Validasi host/port dan kembalikan host yang sudah dinormalisasi."""
    normalized = normalize_host(host)
    if not normalized or len(normalized) > 253:
        raise TlsTargetError("Host tidak valid")
    if not 1 <= port <= 65535:
        raise TlsTargetError("Port harus di antara 1 dan 65535")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        labels = normalized.split(".")
        if any(not _HOST_LABEL_RE.match(label) for label in labels):
            raise TlsTargetError("Hostname tidak valid")
    if not settings.TLS_DOMAIN_ALLOW_PRIVATE_IP and _resolves_to_non_public(
        normalized, port
    ):
        raise TlsTargetError(
            "Host privat/loopback tidak diizinkan. Set TLS_DOMAIN_ALLOW_PRIVATE_IP=true "
            "bila target memang berada di jaringan internal."
        )
    return normalized


def _cache_get(key: str) -> TlsInspection | None:
    ttl = settings.TLS_DOMAIN_CACHE_TTL_SECONDS
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: TlsInspection) -> None:
    ttl = settings.TLS_DOMAIN_CACHE_TTL_SECONDS
    if ttl <= 0:
        return
    expires_at = time.monotonic() + ttl
    with _CACHE_LOCK:
        if len(_CACHE) >= _MAX_CACHE_ENTRIES:
            now = time.monotonic()
            for old_key in [k for k, (exp, _) in _CACHE.items() if exp <= now]:
                _CACHE.pop(old_key, None)
            while len(_CACHE) >= _MAX_CACHE_ENTRIES:
                _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = (expires_at, value)


def clear_inspection_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _fetch_certificate(host: str, port: int, timeout: float) -> tuple[x509.Certificate, str | None]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw:
        raw.settimeout(timeout)
        with context.wrap_socket(raw, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
            protocol = tls.version()
    if not der:
        raise ssl.SSLError("Server tidak mengirim sertifikat")
    return x509.load_der_x509_certificate(der), protocol


def _verify_certificate(host: str, port: int, timeout: float) -> tuple[bool, str | None]:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            raw.settimeout(timeout)
            with context.wrap_socket(raw, server_hostname=host):
                return True, None
    except ssl.SSLCertVerificationError as exc:
        return False, exc.verify_message or str(exc)
    except (ssl.SSLError, OSError) as exc:
        return False, str(exc)


def _name_value(name: x509.Name, oid: x509.ObjectIdentifier) -> str | None:
    values = name.get_attributes_for_oid(oid)
    if not values:
        return None
    return str(values[0].value).strip() or None


def _cert_subject(cert: x509.Certificate) -> str | None:
    return _name_value(cert.subject, NameOID.COMMON_NAME) or _name_value(
        cert.subject, NameOID.ORGANIZATION_NAME
    )


def _cert_issuer(cert: x509.Certificate) -> str | None:
    return _name_value(cert.issuer, NameOID.COMMON_NAME) or _name_value(
        cert.issuer, NameOID.ORGANIZATION_NAME
    )


def _dnsname_matches(pattern: str, hostname: str) -> bool:
    pattern = pattern.rstrip(".").lower()
    hostname = hostname.rstrip(".").lower()
    if pattern == hostname:
        return True
    if not pattern.startswith("*."):
        return False
    suffix = pattern[2:]
    if not suffix or hostname.count(".") != suffix.count(".") + 1:
        return False
    return hostname.endswith("." + suffix)


def _certificate_matches_host(cert: x509.Certificate, host: str) -> bool:
    host = normalize_host(host)
    try:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound:
        san = None

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None

    if address is not None:
        if san is not None:
            return any(item == address for item in san.get_values_for_type(x509.IPAddress))
        return False

    names: list[str] = []
    if san is not None:
        names = [str(item) for item in san.get_values_for_type(x509.DNSName)]
    if not names:
        common_name = _name_value(cert.subject, NameOID.COMMON_NAME)
        names = [common_name] if common_name else []
    return any(_dnsname_matches(name, host) for name in names)


def _is_self_signed(cert: x509.Certificate) -> bool:
    return cert.issuer == cert.subject


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def inspect_target(
    host: str,
    port: int = 443,
    warning_days: int | None = None,
    *,
    use_cache: bool = True,
    now: datetime | None = None,
) -> TlsInspection:
    """Periksa sertifikat target dan kembalikan status tanpa menyentuh database."""
    normalized = validate_target(host, port)
    warning = warning_days or settings.TLS_DOMAIN_EXPIRY_WARNING_DAYS
    checked_at = now or datetime.now(timezone.utc)
    cache_key = f"{normalized}:{port}:{warning}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    timeout = float(settings.TLS_DOMAIN_CHECK_TIMEOUT_SECONDS)
    try:
        cert, protocol = _fetch_certificate(normalized, port, timeout)
    except (TimeoutError, socket.timeout):
        result = TlsInspection(
            status=TlsDomainStatus.error,
            checked_at=checked_at,
            error_message=f"Koneksi TLS timeout setelah {timeout:g} detik",
        )
        _cache_set(cache_key, result)
        return result
    except ssl.SSLError as exc:
        result = TlsInspection(
            status=TlsDomainStatus.error,
            checked_at=checked_at,
            error_message=f"Handshake TLS gagal: {exc}",
        )
        _cache_set(cache_key, result)
        return result
    except OSError as exc:
        result = TlsInspection(
            status=TlsDomainStatus.error,
            checked_at=checked_at,
            error_message=f"Tidak dapat terhubung ke {normalized}:{port}: {exc}",
        )
        _cache_set(cache_key, result)
        return result

    not_after = _utc(cert.not_valid_after_utc)
    not_before = _utc(cert.not_valid_before_utc)
    days_remaining = (not_after - checked_at).days
    base: dict[str, Any] = dict(
        checked_at=checked_at,
        days_remaining=days_remaining,
        expiry_date=not_after,
        issuer=_cert_issuer(cert),
        subject=_cert_subject(cert),
        protocol=protocol,
    )

    if not_before > checked_at:
        result = TlsInspection(
            status=TlsDomainStatus.invalid,
            error_message="Sertifikat belum berlaku",
            **base,
        )
    elif not_after <= checked_at:
        result = TlsInspection(
            status=TlsDomainStatus.expired,
            error_message="Sertifikat sudah kedaluwarsa",
            **base,
        )
    elif _is_self_signed(cert):
        result = TlsInspection(
            status=TlsDomainStatus.invalid,
            error_message="Sertifikat self-signed tidak tepercaya",
            **base,
        )
    elif not _certificate_matches_host(cert, normalized):
        result = TlsInspection(
            status=TlsDomainStatus.invalid,
            error_message=f"Sertifikat tidak cocok untuk host {normalized}",
            **base,
        )
    else:
        verified, verify_error = _verify_certificate(normalized, port, timeout)
        if not verified:
            result = TlsInspection(
                status=TlsDomainStatus.invalid,
                error_message=f"Verifikasi sertifikat gagal: {verify_error}",
                **base,
            )
        else:
            result = TlsInspection(
                status=(
                    TlsDomainStatus.expiring
                    if days_remaining <= warning
                    else TlsDomainStatus.healthy
                ),
                trusted=True,
                **base,
            )

    _cache_set(cache_key, result)
    return result


def _should_notify(domain: TlsDomain, result: TlsInspection) -> bool:
    if not settings.TLS_NOTIFICATIONS_ENABLED or not domain.enabled:
        return False
    if result.status not in _WARNING_STATUSES:
        return False
    if domain.alerted_status != result.status.value:
        return True
    if domain.last_alerted_at is None:
        return True
    last = _utc(domain.last_alerted_at)
    elapsed = (result.checked_at - last).total_seconds()
    return elapsed >= settings.TLS_ALERT_COOLDOWN_SECONDS


def _send_alert(db: Session, domain: TlsDomain, result: TlsInspection) -> bool:
    severity = (
        "critical" if result.status == TlsDomainStatus.expired else "warning"
    )
    days_text = (
        f"{result.days_remaining} hari tersisa"
        if result.days_remaining is not None
        else "sisa hari tidak diketahui"
    )
    description = (
        f"Target TLS {domain.host}:{domain.port} berstatus {result.status.value} "
        f"({days_text})."
    )
    if result.error_message:
        description += f" Detail: {result.error_message}"
    try:
        channels = alert_channel_repository.list_enabled_for_severity(db, severity)
        if not channels:
            return False
        event = alert_service.NotificationEvent(
            alert_name="TlsCertificateIssue",
            status="event",
            severity=severity,
            summary=f"TLS {domain.host}:{domain.port} {result.status.value}",
            description=description,
            labels={
                "event": "tls_domain",
                "domain_id": str(domain.id),
                "host": domain.host,
                "port": str(domain.port),
                "status": result.status.value,
                "days_remaining": str(result.days_remaining or ""),
            },
            annotations={},
            starts_at=result.checked_at,
            ends_at=None,
        )
        sent = False
        for channel in channels:
            try:
                alert_service.send_to_channel(channel, event)
                sent = True
                logger.info(
                    f"Notifikasi TLS {domain.host}:{domain.port} dikirim "
                    f"ke channel {channel.name}."
                )
            except Exception as exc:
                logger.error(
                    f"Gagal mengirim notifikasi TLS {domain.host}:{domain.port} "
                    f"ke channel {channel.name}: {exc}"
                )
        return sent
    except Exception as exc:
        logger.error(f"Gagal menyiapkan notifikasi TLS: {exc}")
        return False


def apply_result(
    db: Session, domain: TlsDomain, result: TlsInspection
) -> tuple[TlsDomain, TlsDomainCheck]:
    """Simpan hasil inspeksi ke domain dan riwayat, plus notifikasi best-effort."""
    previous_status = domain.status
    domain.status = result.status
    domain.days_remaining = result.days_remaining
    domain.expiry_date = result.expiry_date
    domain.issuer = result.issuer
    domain.subject = result.subject
    domain.protocol = result.protocol
    domain.trusted = result.trusted
    domain.error_message = result.error_message
    domain.last_checked_at = result.checked_at

    alert_sent = False
    if _should_notify(domain, result):
        alert_sent = _send_alert(db, domain, result)
        if alert_sent:
            domain.last_alerted_at = result.checked_at
            domain.alerted_status = result.status.value
    if result.status == TlsDomainStatus.healthy and previous_status != result.status:
        domain.alerted_status = None

    check = tls_domain_repository.create_check(
        db,
        tls_domain_id=domain.id,
        status=result.status.value,
        days_remaining=result.days_remaining,
        expiry_date=result.expiry_date,
        issuer=result.issuer,
        subject=result.subject,
        protocol=result.protocol,
        trusted=result.trusted,
        error_message=result.error_message,
        alert_sent=alert_sent,
        checked_at=result.checked_at,
    )
    db.refresh(domain)
    return domain, check


def check_domain(
    db: Session, domain: TlsDomain, *, force: bool = False
) -> tuple[TlsDomain, TlsDomainCheck]:
    result = inspect_target(
        domain.host,
        domain.port,
        domain.warning_days,
        use_cache=not force,
    )
    return apply_result(db, domain, result)
