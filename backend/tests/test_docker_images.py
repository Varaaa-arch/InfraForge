"""
Unit test untuk Step 5 — Docker Image Management (Task 3.4 + 3.13).
Semua test mock Docker client agar tidak butuh Docker daemon nyata.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_image(
    id: str = "sha256:abc123def456",
    tags: list[str] | None = None,
    size: int = 50_000_000,
    created: str = "2024-01-01T00:00:00Z",
    no_tags: bool = False,
) -> MagicMock:
    img = MagicMock()
    img.id = id
    img.tags = [] if no_tags else (tags if tags is not None else ["nginx:latest"])
    img.attrs = {"Size": size, "Created": created}
    return img


def _mock_client(images: list[MagicMock] | None = None) -> MagicMock:
    client = MagicMock()
    client.ping.return_value = True
    client.images.list.return_value = images or []
    return client


# ---------------------------------------------------------------------------
# docker_service unit tests
# ---------------------------------------------------------------------------

class TestDockerServiceListImages:
    def test_returns_list_of_image_info(self) -> None:
        from app.services.docker_service import list_images

        mock_img = _make_mock_image(tags=["ubuntu:22.04", "ubuntu:latest"])
        with patch("app.services.docker_service._get_client", return_value=_mock_client([mock_img])):
            result = list_images()

        assert len(result) == 1
        assert "ubuntu:22.04" in result[0].tags
        assert result[0].size == 50_000_000

    def test_empty_list_when_no_images(self) -> None:
        from app.services.docker_service import list_images

        with patch("app.services.docker_service._get_client", return_value=_mock_client([])):
            result = list_images()

        assert result == []

    def test_image_id_stripped_of_sha256_prefix(self) -> None:
        from app.services.docker_service import list_images

        mock_img = _make_mock_image(id="sha256:deadbeef1234567890ab")
        with patch("app.services.docker_service._get_client", return_value=_mock_client([mock_img])):
            result = list_images()

        assert result[0].id == "deadbeef1234"

    def test_image_with_no_tags_defaults_to_none_tag(self) -> None:
        from app.services.docker_service import list_images

        mock_img = _make_mock_image(no_tags=True)
        with patch("app.services.docker_service._get_client", return_value=_mock_client([mock_img])):
            result = list_images()

        assert result[0].tags == ["<none>:<none>"]

    def test_client_error_raises_runtime_error(self) -> None:
        from app.services.docker_service import list_images

        client = _mock_client()
        client.images.list.side_effect = Exception("daemon not responding")
        with patch("app.services.docker_service._get_client", return_value=client):
            with pytest.raises(RuntimeError, match="Gagal mengambil daftar image"):
                list_images()


class TestDockerServicePullImage:
    def test_pull_success_returns_pull_result(self) -> None:
        from app.services.docker_service import pull_image

        client = _mock_client()
        client.images.pull.return_value = MagicMock()
        with patch("app.services.docker_service._get_client", return_value=client):
            result = pull_image("nginx", "latest")

        assert result.success is True
        assert result.image == "nginx"
        assert result.tag == "latest"
        assert "berhasil" in result.message

    def test_pull_with_custom_tag(self) -> None:
        from app.services.docker_service import pull_image

        client = _mock_client()
        with patch("app.services.docker_service._get_client", return_value=client):
            result = pull_image("python", "3.12-slim")

        client.images.pull.assert_called_once_with("python", tag="3.12-slim")
        assert result.tag == "3.12-slim"

    def test_pull_failure_returns_result_with_success_false(self) -> None:
        from app.services.docker_service import pull_image

        client = _mock_client()
        client.images.pull.side_effect = Exception("image not found in registry")
        with patch("app.services.docker_service._get_client", return_value=client):
            result = pull_image("nonexistent/image", "v99")

        assert result.success is False
        assert "gagal" in result.message.lower()


class TestDockerServiceRemoveImage:
    def test_remove_success(self) -> None:
        from app.services.docker_service import remove_image

        client = _mock_client()
        with patch("app.services.docker_service._get_client", return_value=client):
            remove_image("abc123def456")

        client.images.remove.assert_called_once_with("abc123def456", force=False)

    def test_remove_with_force(self) -> None:
        from app.services.docker_service import remove_image

        client = _mock_client()
        with patch("app.services.docker_service._get_client", return_value=client):
            remove_image("abc123", force=True)

        client.images.remove.assert_called_once_with("abc123", force=True)

    def test_remove_image_not_found_raises_runtime_error(self) -> None:
        import docker.errors

        from app.services.docker_service import remove_image

        client = _mock_client()
        client.images.remove.side_effect = docker.errors.ImageNotFound("not found")
        with patch("app.services.docker_service._get_client", return_value=client):
            with pytest.raises(RuntimeError, match="tidak ditemukan"):
                remove_image("ghost_image")

    def test_remove_generic_error_raises_runtime_error(self) -> None:
        from app.services.docker_service import remove_image

        client = _mock_client()
        client.images.remove.side_effect = Exception("permission denied")
        with patch("app.services.docker_service._get_client", return_value=client):
            with pytest.raises(RuntimeError, match="Gagal menghapus"):
                remove_image("img123")


# ---------------------------------------------------------------------------
# Docker API endpoint tests
# ---------------------------------------------------------------------------

class TestDockerImageEndpoints:
    def _login(self, client: object) -> dict[str, str]:
        import uuid
        c = client  # type: ignore[assignment]
        suffix = uuid.uuid4().hex[:8]
        user = {"username": f"u_{suffix}", "email": f"u_{suffix}@x.com", "password": "pass1234"}
        c.post("/auth/register", json=user)  # type: ignore[attr-defined]
        r = c.post("/auth/login", data={"username": user["username"], "password": user["password"]})  # type: ignore[attr-defined]
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    def test_list_images_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_img = _make_mock_image()
        with patch("app.services.docker_service._get_client", return_value=_mock_client([mock_img])):
            r = c.get("/docker/images", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_list_images_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.get("/docker/images")
        assert r.status_code == 401

    def test_pull_image_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_c = _mock_client()
        with patch("app.services.docker_service._get_client", return_value=mock_c):
            r = c.post("/docker/images/pull", headers=headers, json={"image": "alpine", "tag": "latest"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["image"] == "alpine"
        assert data["success"] is True

    def test_pull_image_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.post("/docker/images/pull", json={"image": "alpine"})
        assert r.status_code == 401

    def test_delete_image_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_c = _mock_client()
        with patch("app.services.docker_service._get_client", return_value=mock_c):
            r = c.delete("/docker/images/abc123", headers=headers)
        assert r.status_code == 200
        assert "berhasil" in r.json()["data"]["message"]

    def test_delete_image_not_found_returns_404(self, client: object) -> None:
        import docker.errors
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_c = _mock_client()
        mock_c.images.remove.side_effect = docker.errors.ImageNotFound("nf")
        with patch("app.services.docker_service._get_client", return_value=mock_c):
            r = c.delete("/docker/images/ghost", headers=headers)
        assert r.status_code == 404

    def test_list_images_daemon_down_returns_503(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        with patch(
            "app.services.docker_service._get_client",
            side_effect=RuntimeError("daemon not reachable"),
        ):
            r = c.get("/docker/images", headers=headers)
        assert r.status_code == 503
