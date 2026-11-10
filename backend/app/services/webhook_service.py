"""
Webhook Service — validasi signature HMAC SHA-256 dan matching aplikasi.

Tanggung jawab modul ini:
  1. verify_signature   — verifikasi X-Hub-Signature-256 menggunakan constant-time comparison.
  2. extract_branch     — parse ref dari push payload ke nama branch.
  3. find_matching_apps  — cari aplikasi yang repository-nya match dengan push event.

Keamanan:
  - Menggunakan hmac.compare_digest (constant-time) untuk mencegah timing attack.
  - Signature dihitung dari raw body bytes, bukan parsed JSON.
  - Secret diambil dari settings.GITHUB_WEBHOOK_SECRET.
"""

from __future__ import annotations

import hashlib
import hmac

from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.repositories import application_repository


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Verifikasi GitHub webhook signature menggunakan HMAC SHA-256.

    GitHub mengirim header:
        X-Hub-Signature-256: sha256=<hex_digest>

    Signature dihitung dari raw request body (sebelum parsing JSON).

    Args:
        raw_body:        Raw bytes dari request body.
        signature_header: Isi header X-Hub-Signature-256.

    Returns:
        True jika signature valid, False jika tidak.
    """
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        # Jika secret tidak dikonfigurasi, tolak semua webhook (fail-closed).
        return False

    if not signature_header:
        return False

    # Format: "sha256=<hex>"
    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False

    received_hash = signature_header[len(expected_prefix):]

    # Hitung HMAC SHA-256 dari raw body
    computed = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison untuk mencegah timing attack
    return hmac.compare_digest(computed, received_hash)


def extract_branch(ref: str) -> str | None:
    """
    Extract nama branch dari GitHub ref.

    Args:
        ref: Format GitHub, misal "refs/heads/main" atau "refs/tags/v1.0".

    Returns:
        Nama branch jika ref adalah branch ("refs/heads/xxx"),
        None jika ref adalah tag atau format lain.
    """
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix):]
    return None


def find_matching_applications(
    db: Session,
    repository_url: str,
    branch: str,
) -> list[Application]:
    """
    Cari semua aplikasi yang repository URL-nya match dengan push event
    dan branch-nya sama.

    Matching dilakukan dengan normalisasi URL (strip trailing slash, .git suffix)
    lalu comparison case-insensitive.

    Args:
        db:             Session database.
        repository_url: URL repository dari webhook payload (html_url atau clone_url).
        branch:         Branch yang di-push.

    Returns:
        List aplikasi yang match. Bisa kosong jika tidak ada yang match.
    """
    normalized_repo = _normalize_repo_url(repository_url)

    all_apps = application_repository.list_all_with_repository(db)
    matching: list[Application] = []

    for app in all_apps:
        if app.repository is None:
            continue
        app_repo = _normalize_repo_url(app.repository)
        if app_repo == normalized_repo and app.branch == branch:
            matching.append(app)

    return matching


def _normalize_repo_url(url: str) -> str:
    """
    Normalisasi URL repository untuk perbandingan yang reliable.

    - Strip trailing slash
    - Strip .git suffix
    - Lowercase (URL GitHub case-insensitive untuk path)
    """
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[: -len(".git")]
    return url.lower()
