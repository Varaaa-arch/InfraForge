"""
Git Service — clone dan checkout repository menggunakan GitPython.

Mendukung:
- Repository publik via HTTPS
- Repository privat via HTTPS (dengan username/token di URL)
- Repository privat via SSH key (private key string)

Semua clone dilakukan ke direktori tmp/ di root backend.
Setiap clone mendapat subdirektori unik berbasis UUID untuk menghindari collision.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# tmp/ relatif terhadap working directory saat runtime
_TMP_BASE = Path("tmp")


@dataclass
class CloneResult:
    """Hasil operasi clone repository."""

    repo_dir: Path
    branch: str
    commit_sha: str
    success: bool
    message: str


def _ensure_tmp_dir() -> Path:
    """Pastikan direktori tmp/ ada. Buat jika belum."""
    _TMP_BASE.mkdir(parents=True, exist_ok=True)
    return _TMP_BASE


def _build_https_url_with_token(url: str, username: str, token: str) -> str:
    """
    Sisipkan credentials ke HTTPS URL.
    https://github.com/org/repo → https://user:token@github.com/org/repo
    """
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    return f"{scheme}://{username}:{token}@{rest}"


def clone_repository(
    url: str,
    branch: str = "main",
    *,
    username: str | None = None,
    token: str | None = None,
    ssh_key: str | None = None,
    depth: int | None = 1,
) -> CloneResult:
    """
    Clone repository Git ke direktori sementara di tmp/.

    Args:
        url:      URL repository (https:// atau git@).
        branch:   Branch yang akan di-clone dan di-checkout.
        username: Username untuk HTTPS auth (opsional).
        token:    Personal access token untuk HTTPS auth (opsional).
        ssh_key:  Isi private key SSH sebagai string (opsional).
        depth:    Shallow clone depth. None untuk full clone.

    Returns:
        CloneResult dengan path direktori hasil clone dan metadata.

    Raises:
        RuntimeError: Jika clone gagal karena alasan apapun.
    """
    try:
        import git
        from git import GitCommandError, InvalidGitRepositoryError
    except ImportError as exc:
        raise ImportError(
            "gitpython diperlukan. Install dengan: uv add gitpython"
        ) from exc

    _ensure_tmp_dir()
    clone_dir = _TMP_BASE / str(uuid.uuid4())

    # Siapkan URL dengan credentials jika diperlukan
    clone_url = url
    if token and url.startswith("http"):
        clone_url = _build_https_url_with_token(
            url, username or "oauth2", token
        )

    # Siapkan SSH env jika menggunakan private key
    env: dict[str, str] | None = None
    key_file_path: str | None = None

    if ssh_key and url.startswith("git@"):
        key_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        )
        key_file.write(ssh_key)
        key_file.flush()
        key_file.close()
        key_file_path = key_file.name
        env = {
            "GIT_SSH_COMMAND": (
                f"ssh -i {key_file_path} "
                "-o StrictHostKeyChecking=no "
                "-o UserKnownHostsFile=/dev/null"
            )
        }

    try:
        clone_kwargs: dict[str, object] = {
            "branch": branch,
            "no_single_branch": False,
        }
        if depth is not None:
            clone_kwargs["depth"] = depth
        if env:
            clone_kwargs["env"] = env

        logger.info(f"Cloning {url} branch={branch} → {clone_dir}")
        repo = git.Repo.clone_from(clone_url, clone_dir, **clone_kwargs)  # type: ignore[arg-type]

        commit_sha = repo.head.commit.hexsha
        logger.info(f"Clone berhasil: {commit_sha[:8]} @ {branch}")

        return CloneResult(
            repo_dir=clone_dir,
            branch=branch,
            commit_sha=commit_sha,
            success=True,
            message=f"Clone berhasil pada commit {commit_sha[:8]}",
        )

    except (GitCommandError, InvalidGitRepositoryError, Exception) as exc:
        # Bersihkan direktori yang mungkin sudah terbuat
        if clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)
        logger.error(f"Clone gagal [{url}]: {exc}")
        raise RuntimeError(f"Clone gagal: {exc}") from exc

    finally:
        if key_file_path is not None:
            Path(key_file_path).unlink(missing_ok=True)


def checkout_branch(repo_dir: Path, branch: str) -> str:
    """
    Checkout ke branch tertentu pada repository yang sudah di-clone.

    Args:
        repo_dir: Path direktori hasil clone.
        branch:   Nama branch yang dituju.

    Returns:
        Commit SHA setelah checkout.

    Raises:
        RuntimeError: Jika checkout gagal.
    """
    try:
        import git
        from git import GitCommandError
    except ImportError as exc:
        raise ImportError("gitpython diperlukan.") from exc

    try:
        repo = git.Repo(repo_dir)
        repo.git.checkout(branch)
        sha = repo.head.commit.hexsha
        logger.info(f"Checkout {branch} → {sha[:8]}")
        return sha
    except (GitCommandError, Exception) as exc:
        raise RuntimeError(f"Checkout gagal ke branch '{branch}': {exc}") from exc


def cleanup(repo_dir: Path) -> None:
    """
    Hapus direktori hasil clone setelah selesai digunakan.
    Aman dipanggil meski direktori tidak ada (no-op).
    """
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
        logger.debug(f"Cleaned up {repo_dir}")
