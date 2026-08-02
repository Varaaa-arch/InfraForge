"""
Unit test untuk Step 4 — Git Integration (Task 3.3 + 3.13).

Semua test menggunakan mock untuk menghindari koneksi jaringan nyata.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_repo(sha: str = "abc1234567890abc") -> MagicMock:
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = sha
    return mock_repo


# ---------------------------------------------------------------------------
# clone_repository — success paths
# ---------------------------------------------------------------------------

class TestCloneRepository:
    def test_clone_public_https_success(self, tmp_path: Path) -> None:
        """Clone HTTPS publik berhasil → CloneResult dengan success=True."""
        from app.services.git_service import clone_repository

        mock_repo = _make_mock_repo("deadbeef1234")

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=mock_repo) as mock_clone,
        ):
            result = clone_repository("https://github.com/org/repo.git", branch="main")

        assert result.success is True
        assert result.branch == "main"
        assert result.commit_sha == "deadbeef1234"
        assert "deadbeef" in result.message
        mock_clone.assert_called_once()
        # URL tidak boleh mengandung credentials karena tidak ada token
        call_url = mock_clone.call_args[0][0]
        assert "@" not in call_url.replace("https://", "")

    def test_clone_with_token_injects_credentials(self, tmp_path: Path) -> None:
        """Clone HTTPS dengan token → URL harus mengandung credentials."""
        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()) as mock_clone,
        ):
            result = clone_repository(
                "https://github.com/org/private.git",
                branch="develop",
                username="myuser",
                token="ghp_secrettoken",
            )

        assert result.success is True
        call_url = mock_clone.call_args[0][0]
        assert "myuser:ghp_secrettoken" in call_url

    def test_clone_with_token_default_oauth2_username(self, tmp_path: Path) -> None:
        """Clone dengan token tapi tanpa username → default ke 'oauth2'."""
        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()) as mock_clone,
        ):
            clone_repository(
                "https://github.com/org/private.git",
                token="token123",
            )

        call_url = mock_clone.call_args[0][0]
        assert "oauth2:token123" in call_url

    def test_clone_result_contains_repo_dir(self, tmp_path: Path) -> None:
        """CloneResult.repo_dir harus berupa Path."""
        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()),
        ):
            result = clone_repository("https://github.com/org/repo.git")

        assert isinstance(result.repo_dir, Path)

    def test_clone_custom_branch(self, tmp_path: Path) -> None:
        """Branch yang diberikan harus diteruskan ke clone_from."""
        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()) as mock_clone,
        ):
            clone_repository("https://github.com/org/repo.git", branch="release/v2")

        kwargs = mock_clone.call_args[1]
        assert kwargs.get("branch") == "release/v2"

    def test_clone_shallow_depth_passed(self, tmp_path: Path) -> None:
        """depth=1 (shallow clone) harus diteruskan ke clone_from."""
        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()) as mock_clone,
        ):
            clone_repository("https://github.com/org/repo.git", depth=1)

        kwargs = mock_clone.call_args[1]
        assert kwargs.get("depth") == 1

    def test_clone_full_no_depth_when_none(self, tmp_path: Path) -> None:
        """depth=None → 'depth' tidak boleh ada di kwargs."""
        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()) as mock_clone,
        ):
            clone_repository("https://github.com/org/repo.git", depth=None)

        kwargs = mock_clone.call_args[1]
        assert "depth" not in kwargs

    def test_clone_ssh_sets_git_ssh_command(self, tmp_path: Path) -> None:
        """SSH key → GIT_SSH_COMMAND env harus di-set dan diteruskan."""
        from app.services.git_service import clone_repository

        ssh_key = "-----BEGIN RSA PRIVATE KEY-----\nfakekey\n-----END RSA PRIVATE KEY-----"

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()) as mock_clone,
            patch("tempfile.NamedTemporaryFile") as mock_tmpfile,
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/fake_key.pem"
            mock_tmpfile.return_value.__enter__ = MagicMock(return_value=mock_file)
            mock_tmpfile.return_value = mock_file

            clone_repository(
                "git@github.com:org/private.git",
                ssh_key=ssh_key,
            )

        kwargs = mock_clone.call_args[1]
        env = kwargs.get("env", {})
        assert "GIT_SSH_COMMAND" in env
        assert "StrictHostKeyChecking=no" in env["GIT_SSH_COMMAND"]


# ---------------------------------------------------------------------------
# clone_repository — failure paths
# ---------------------------------------------------------------------------

class TestCloneRepositoryFailures:
    def test_clone_git_error_raises_runtime_error(self, tmp_path: Path) -> None:
        """GitCommandError harus di-wrap jadi RuntimeError."""
        import git

        from app.services.git_service import clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch(
                "git.Repo.clone_from",
                side_effect=git.GitCommandError("clone", "Repository not found"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Clone gagal"):
                clone_repository("https://github.com/org/nonexistent.git")

    def test_clone_failure_cleans_up_dir(self, tmp_path: Path) -> None:
        """Saat clone gagal, direktori yang sudah dibuat harus dibersihkan."""
        import git

        from app.services.git_service import clone_repository

        # Buat dir "palsu" yang ada sebelum clone
        created_dir: list[Path] = []

        def fake_clone(url: str, to_path: object, **kwargs: object) -> None:
            p = Path(str(to_path))
            p.mkdir(parents=True, exist_ok=True)
            created_dir.append(p)
            raise git.GitCommandError("clone", "auth failed")

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", side_effect=fake_clone),
        ):
            with pytest.raises(RuntimeError):
                clone_repository("https://github.com/org/repo.git")

        # Direktori harus sudah dihapus
        if created_dir:
            assert not created_dir[0].exists()


# ---------------------------------------------------------------------------
# checkout_branch
# ---------------------------------------------------------------------------

class TestCheckoutBranch:
    def test_checkout_returns_commit_sha(self, tmp_path: Path) -> None:
        """checkout_branch harus return SHA commit setelah checkout."""
        from app.services.git_service import checkout_branch

        mock_repo = _make_mock_repo("feedface1234567")

        with patch("git.Repo", return_value=mock_repo):
            sha = checkout_branch(tmp_path, "feature/new-ui")

        assert sha == "feedface1234567"
        mock_repo.git.checkout.assert_called_once_with("feature/new-ui")

    def test_checkout_invalid_branch_raises_runtime_error(self, tmp_path: Path) -> None:
        """Branch yang tidak ada harus raise RuntimeError."""
        import git

        from app.services.git_service import checkout_branch

        mock_repo = MagicMock()
        mock_repo.git.checkout.side_effect = git.GitCommandError(
            "checkout", "pathspec 'ghost-branch' did not match"
        )

        with patch("git.Repo", return_value=mock_repo):
            with pytest.raises(RuntimeError, match="Checkout gagal"):
                checkout_branch(tmp_path, "ghost-branch")

    def test_checkout_calls_git_checkout_with_branch(self, tmp_path: Path) -> None:
        """git.checkout harus dipanggil dengan nama branch yang diberikan."""
        from app.services.git_service import checkout_branch

        mock_repo = _make_mock_repo()
        with patch("git.Repo", return_value=mock_repo):
            checkout_branch(tmp_path, "hotfix/critical")

        mock_repo.git.checkout.assert_called_with("hotfix/critical")


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_cleanup_removes_directory(self, tmp_path: Path) -> None:
        """cleanup harus menghapus direktori yang ada."""
        from app.services.git_service import cleanup

        target = tmp_path / "repo_clone"
        target.mkdir()
        (target / "file.txt").write_text("content")

        cleanup(target)
        assert not target.exists()

    def test_cleanup_nonexistent_dir_is_noop(self, tmp_path: Path) -> None:
        """cleanup pada direktori yang tidak ada tidak boleh raise exception."""
        from app.services.git_service import cleanup

        non_existent = tmp_path / "does_not_exist"
        # Tidak boleh raise
        cleanup(non_existent)

    def test_cleanup_called_after_successful_clone(self, tmp_path: Path) -> None:
        """Setelah clone sukses, cleanup harus menghapus repo_dir."""
        from app.services.git_service import cleanup, clone_repository

        with (
            patch("app.services.git_service._TMP_BASE", tmp_path),
            patch("git.Repo.clone_from", return_value=_make_mock_repo()),
        ):
            result = clone_repository("https://github.com/org/repo.git")
            # Buat dir agar cleanup bisa diverifikasi
            result.repo_dir.mkdir(parents=True, exist_ok=True)

        cleanup(result.repo_dir)
        assert not result.repo_dir.exists()


# ---------------------------------------------------------------------------
# URL builder helper
# ---------------------------------------------------------------------------

class TestBuildHttpsUrlWithToken:
    def test_injects_credentials_correctly(self) -> None:
        from app.services.git_service import _build_https_url_with_token  # type: ignore[attr-defined]

        result = _build_https_url_with_token(
            "https://github.com/org/repo.git", "user", "token"
        )
        assert result == "https://user:token@github.com/org/repo.git"

    def test_url_without_scheme_returned_unchanged(self) -> None:
        from app.services.git_service import _build_https_url_with_token  # type: ignore[attr-defined]

        result = _build_https_url_with_token("github.com/org/repo", "u", "t")
        assert result == "github.com/org/repo"
