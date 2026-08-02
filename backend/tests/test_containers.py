"""
Unit test untuk Step 6 — Container Management (Task 3.5 + 3.13).
Semua test mock Docker client.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_container(
    short_id: str = "abc123def456",
    name: str = "web_1",
    status: str = "running",
    image_tags: list[str] | None = None,
    no_tags: bool = False,
) -> MagicMock:
    c = MagicMock()
    c.short_id = short_id
    c.name = name
    c.status = status
    img = MagicMock()
    img.tags = [] if no_tags else (image_tags if image_tags is not None else ["nginx:latest"])
    img.short_id = "imgshort"
    c.image = img
    c.attrs = {"Created": "2024-01-01T00:00:00Z"}
    return c


def _mock_client(containers: list[MagicMock] | None = None) -> MagicMock:
    client = MagicMock()
    client.ping.return_value = True
    client.containers.list.return_value = containers or []
    return client


# ---------------------------------------------------------------------------
# container_service unit tests
# ---------------------------------------------------------------------------

class TestContainerServiceList:
    def test_returns_list_of_container_info(self) -> None:
        from app.services.container_service import list_containers

        c = _make_container(status="running")
        with patch("app.services.container_service._get_client", return_value=_mock_client([c])):
            result = list_containers()

        assert len(result) == 1
        assert result[0].name == "web_1"
        assert result[0].status == "running"

    def test_empty_list_when_no_containers(self) -> None:
        from app.services.container_service import list_containers

        with patch("app.services.container_service._get_client", return_value=_mock_client([])):
            result = list_containers()
        assert result == []

    def test_all_true_passes_to_docker_client(self) -> None:
        from app.services.container_service import list_containers

        client = _mock_client()
        with patch("app.services.container_service._get_client", return_value=client):
            list_containers(all_containers=True)

        client.containers.list.assert_called_once_with(all=True)

    def test_all_false_passes_to_docker_client(self) -> None:
        from app.services.container_service import list_containers

        client = _mock_client()
        with patch("app.services.container_service._get_client", return_value=client):
            list_containers(all_containers=False)

        client.containers.list.assert_called_once_with(all=False)

    def test_container_image_fallback_to_short_id_when_no_tags(self) -> None:
        from app.services.container_service import list_containers

        c = _make_container(no_tags=True)
        with patch("app.services.container_service._get_client", return_value=_mock_client([c])):
            result = list_containers()

        assert result[0].image == "imgshort"

    def test_daemon_error_raises_runtime_error(self) -> None:
        from app.services.container_service import list_containers

        client = _mock_client()
        client.containers.list.side_effect = Exception("connection refused")
        with patch("app.services.container_service._get_client", return_value=client):
            with pytest.raises(RuntimeError, match="Gagal mengambil daftar container"):
                list_containers()


class TestContainerServiceLifecycle:
    def _setup(self, container: MagicMock) -> MagicMock:
        client = _mock_client()
        client.containers.get.return_value = container
        return client

    def test_start_calls_container_start(self) -> None:
        from app.services.container_service import start_container

        c = _make_container()
        client = self._setup(c)
        with patch("app.services.container_service._get_client", return_value=client):
            start_container("abc123")
        c.start.assert_called_once()

    def test_stop_calls_container_stop_with_timeout(self) -> None:
        from app.services.container_service import stop_container

        c = _make_container()
        client = self._setup(c)
        with patch("app.services.container_service._get_client", return_value=client):
            stop_container("abc123", timeout=5)
        c.stop.assert_called_once_with(timeout=5)

    def test_restart_calls_container_restart(self) -> None:
        from app.services.container_service import restart_container

        c = _make_container()
        client = self._setup(c)
        with patch("app.services.container_service._get_client", return_value=client):
            restart_container("abc123", timeout=15)
        c.restart.assert_called_once_with(timeout=15)

    def test_remove_calls_container_remove(self) -> None:
        from app.services.container_service import remove_container

        c = _make_container()
        client = self._setup(c)
        with patch("app.services.container_service._get_client", return_value=client):
            remove_container("abc123", force=True)
        c.remove.assert_called_once_with(force=True)

    def test_container_not_found_raises_runtime_error(self) -> None:
        import docker.errors
        from app.services.container_service import start_container

        client = _mock_client()
        client.containers.get.side_effect = docker.errors.NotFound("not found")
        with patch("app.services.container_service._get_client", return_value=client):
            with pytest.raises(RuntimeError, match="tidak ditemukan"):
                start_container("ghost_container")

    def test_start_error_raises_runtime_error(self) -> None:
        from app.services.container_service import start_container

        c = _make_container()
        c.start.side_effect = Exception("already running")
        client = self._setup(c)
        with patch("app.services.container_service._get_client", return_value=client):
            with pytest.raises(RuntimeError, match="Gagal start"):
                start_container("abc123")


class TestContainerServiceLogs:
    def test_returns_decoded_log_string(self) -> None:
        from app.services.container_service import get_logs

        c = _make_container()
        c.logs.return_value = b"line1\nline2\nline3\n"
        client = _mock_client()
        client.containers.get.return_value = c
        with patch("app.services.container_service._get_client", return_value=client):
            result = get_logs("abc123", tail=10)
        assert "line1" in result
        assert "line3" in result

    def test_logs_passes_tail_and_timestamps(self) -> None:
        from app.services.container_service import get_logs

        c = _make_container()
        c.logs.return_value = b""
        client = _mock_client()
        client.containers.get.return_value = c
        with patch("app.services.container_service._get_client", return_value=client):
            get_logs("abc123", tail=50, timestamps=True)
        c.logs.assert_called_once_with(stdout=True, stderr=True, tail=50, timestamps=True)


class TestContainerServiceInspect:
    def test_returns_dict(self) -> None:
        from app.services.container_service import inspect_container

        c = _make_container()
        c.attrs = {"Id": "abc123", "State": {"Status": "running"}}
        client = _mock_client()
        client.containers.get.return_value = c
        with patch("app.services.container_service._get_client", return_value=client):
            result = inspect_container("abc123")
        assert result["Id"] == "abc123"
        assert result["State"]["Status"] == "running"


# ---------------------------------------------------------------------------
# Container API endpoint tests
# ---------------------------------------------------------------------------

class TestContainerEndpoints:
    def _login(self, client: object) -> dict[str, str]:
        import uuid
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        suffix = uuid.uuid4().hex[:8]
        user = {"username": f"u_{suffix}", "email": f"u_{suffix}@x.com", "password": "pass1234"}
        c.post("/auth/register", json=user)
        r = c.post("/auth/login", data={"username": user["username"], "password": user["password"]})
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    def test_list_containers_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_c = _mock_client([_make_container()])
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.get("/containers", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_list_containers_without_auth_returns_401(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        r = c.get("/containers")
        assert r.status_code == 401

    def test_start_container_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_container = _make_container()
        mock_c = _mock_client()
        mock_c.containers.get.return_value = mock_container
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.post("/containers/abc123/start", headers=headers)
        assert r.status_code == 200

    def test_stop_container_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_container = _make_container()
        mock_c = _mock_client()
        mock_c.containers.get.return_value = mock_container
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.post("/containers/abc123/stop", headers=headers)
        assert r.status_code == 200

    def test_restart_container_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_container = _make_container()
        mock_c = _mock_client()
        mock_c.containers.get.return_value = mock_container
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.post("/containers/abc123/restart", headers=headers)
        assert r.status_code == 200

    def test_delete_container_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_container = _make_container()
        mock_c = _mock_client()
        mock_c.containers.get.return_value = mock_container
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.delete("/containers/abc123", headers=headers)
        assert r.status_code == 200

    def test_container_not_found_returns_404(self, client: object) -> None:
        import docker.errors
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_c = _mock_client()
        mock_c.containers.get.side_effect = docker.errors.NotFound("nf")
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.post("/containers/ghost/start", headers=headers)
        assert r.status_code == 404

    def test_get_logs_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_container = _make_container()
        mock_container.logs.return_value = b"hello logs\n"
        mock_c = _mock_client()
        mock_c.containers.get.return_value = mock_container
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.get("/containers/abc123/logs", headers=headers)
        assert r.status_code == 200
        assert "hello logs" in r.json()["data"]["logs"]

    def test_inspect_container_returns_200(self, client: object) -> None:
        from fastapi.testclient import TestClient
        c: TestClient = client  # type: ignore[assignment]
        headers = self._login(c)
        mock_container = _make_container()
        mock_container.attrs = {"Id": "abc123full", "State": {"Status": "running"}}
        mock_c = _mock_client()
        mock_c.containers.get.return_value = mock_container
        with patch("app.services.container_service._get_client", return_value=mock_c):
            r = c.get("/containers/abc123/inspect", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["Id"] == "abc123full"
