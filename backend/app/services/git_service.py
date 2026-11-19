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
    tag: str | None = None


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


def _tag_at_head(repo: object) -> str | None:
    """Ambil satu tag yang menunjuk tepat ke HEAD, jika ada."""
    try:
        raw = repo.git.tag("--points-at", "HEAD")  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug(f"Gagal mendeteksi tag pada HEAD: {exc}")
        return None
    if not isinstance(raw, str):
        return None
    tags = sorted({line.strip() for line in raw.splitlines() if line.strip()})
    return tags[0] if tags else None


def clone_repository(
    url: str,
    branch: str = "main",
    *,
    username: str | None = None,
    token: str | None = None,
    ssh_key: str | None = None,
    depth: int | None = 1,
    tag: str | None = None,
    commit_sha: str | None = None,
) -> CloneResult:
    """
    Clone repository Git ke direktori sementara di tmp/.

    Mode checkout:
      - ``commit_sha`` diisi → full clone lalu checkout commit exact. Dipakai
        rollback agar kode yang dijalankan benar-benar versi target.
      - ``tag`` diisi (tanpa commit) → clone shallow pada tag tersebut.
      - keduanya kosong → clone branch seperti biasa.

    Args:
        url:        URL repository (https:// atau git@).
        branch:     Branch metadata/checkout default.
        username:   Username untuk HTTPS auth (opsional).
        token:      Personal access token untuk HTTPS auth (opsional).
        ssh_key:    Isi private key SSH sebagai string (opsional).
        depth:      Shallow clone depth. None untuk full clone.
        tag:        Git tag target (opsional).
        commit_sha: Commit SHA exact yang wajib di-checkout (opsional).

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
        if commit_sha is not None:
            # Commit exact hanya bisa dijamin lewat full clone.
            clone_kwargs: dict[str, object] = {"no_single_branch": True}
        else:
            checkout_ref = tag or branch
            clone_kwargs = {
                "branch": checkout_ref,
                "no_single_branch": False,
            }
        effective_depth = None if commit_sha is not None else depth
        if effective_depth is not None:
            clone_kwargs["depth"] = effective_depth
        if env:
            clone_kwargs["env"] = env

        target_label = commit_sha or tag or branch
        logger.info(f"Cloning {url} target={target_label} → {clone_dir}")
        repo = git.Repo.clone_from(clone_url, clone_dir, **clone_kwargs)  # type: ignore[arg-type]

        if commit_sha is not None:
            try:
                repo.git.checkout(commit_sha)
            except GitCommandError:
                # Commit mungkin tidak terjangkau ref default; coba fetch eksplisit.
                repo.git.fetch("origin", commit_sha, depth=1)
                repo.git.checkout(commit_sha)

        actual_sha = repo.head.commit.hexsha
        if commit_sha is not None and not actual_sha.lower().startswith(
            commit_sha.lower()
        ):
            raise RuntimeError(
                f"Commit hasil checkout ({actual_sha}) tidak cocok dengan "
                f"target rollback ({commit_sha})."
            )

        resolved_tag = tag or _tag_at_head(repo)
        logger.info(
            f"Clone berhasil: {actual_sha[:8]} @ {target_label}"
            + (f" tag={resolved_tag}" if resolved_tag else "")
        )

        return CloneResult(
            repo_dir=clone_dir,
            branch=branch,
            commit_sha=actual_sha,
            success=True,
            message=f"Clone berhasil pada commit {actual_sha[:8]}",
            tag=resolved_tag,
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


def get_tag_at_head(repo_dir: Path) -> str | None:
    """Ambil satu tag yang menunjuk tepat ke HEAD pada repo hasil clone."""
    try:
        import git
    except ImportError as exc:
        raise ImportError("gitpython diperlukan.") from exc

    try:
        return _tag_at_head(git.Repo(repo_dir))
    except Exception as exc:
        logger.debug(f"Gagal membuka repo untuk deteksi tag: {exc}")
        return None


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
