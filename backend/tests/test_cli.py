"""
Unit test untuk Task 3.12 — InfraForge CLI.

Semua HTTP request di-mock dengan unittest.mock.patch sehingga test
berjalan independen tanpa server yang aktif.

Coverage:
- _load_config / _save_config
- _get_base_url / _get_token / _auth_headers helpers
- _request HTTP helper (success, ConnectError, TimeoutException)
- config command
- login command (success, wrong password, bad response)
- logout command
- deploy command (success, 404, 401, server error)
- status command (success, 404, 401, server error)
- logs command (no log_path, file exists, file missing, tail, 404, 401)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from app.cli import app, _load_config, _save_config, _get_base_url, _get_token

import re

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text for reliable substring matching."""
    return re.sub(r"\x1b\[[0-9;]*[mGKHF]", "", text)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override CONFIG_DIR dan CONFIG_FILE ke tmp_path untuk isolasi per test."""
    cfg_dir = tmp_path / ".infraforge"
    cfg_file = cfg_dir / "config.json"
    monkeypatch.setattr("app.cli.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("app.cli.CONFIG_FILE", cfg_file)
    return cfg_file


def _write_config(cfg_file: Path, data: dict) -> None:  # type: ignore[type-arg]
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps(data))


def _mock_response(status_code: int, body: dict) -> MagicMock:  # type: ignore[type-arg]
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


# ---------------------------------------------------------------------------
# Unit: _load_config / _save_config
# ---------------------------------------------------------------------------

class TestLoadSaveConfig:
    def test_load_returns_empty_when_file_missing(
        self, tmp_config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _load_config()
        assert result == {}

    def test_save_then_load_roundtrip(self, tmp_config: Path) -> None:
        data = {"base_url": "http://localhost:8000", "token": "abc"}
        _save_config(data)
        assert _load_config() == data

    def test_load_returns_empty_on_malformed_json(self, tmp_config: Path) -> None:
        tmp_config.parent.mkdir(parents=True, exist_ok=True)
        tmp_config.write_text("{ not valid json")
        assert _load_config() == {}

    def test_save_creates_parent_dirs(self, tmp_config: Path) -> None:
        _save_config({"key": "val"})
        assert tmp_config.exists()


# ---------------------------------------------------------------------------
# Unit: _get_base_url / _get_token
# ---------------------------------------------------------------------------

class TestConfigHelpers:
    def test_get_base_url_returns_url(self) -> None:
        cfg = {"base_url": "http://api.example.com"}
        assert _get_base_url(cfg) == "http://api.example.com"

    def test_get_base_url_exits_when_missing(self) -> None:
        from typer import Exit
        with pytest.raises(Exit):
            _get_base_url({})

    def test_get_token_returns_token(self) -> None:
        cfg = {"token": "mytoken123"}
        assert _get_token(cfg) == "mytoken123"

    def test_get_token_exits_when_missing(self) -> None:
        from typer import Exit
        with pytest.raises(Exit):
            _get_token({})


# ---------------------------------------------------------------------------
# Unit: _request helper
# ---------------------------------------------------------------------------

class TestRequestHelper:
    def test_returns_response_on_success(self) -> None:
        from app.cli import _request

        mock_resp = _mock_response(200, {"ok": True})
        with patch("httpx.request", return_value=mock_resp):
            resp = _request("GET", "http://localhost/test")
        assert resp.status_code == 200

    def test_raises_exit_on_connect_error(self) -> None:
        from app.cli import _request
        from typer import Exit

        with patch("httpx.request", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(Exit):
                _request("GET", "http://localhost/test")

    def test_raises_exit_on_timeout(self) -> None:
        from app.cli import _request
        from typer import Exit

        with patch("httpx.request", side_effect=httpx.TimeoutException("timeout")):
            with pytest.raises(Exit):
                _request("GET", "http://localhost/test")


# ---------------------------------------------------------------------------
# Command: config
# ---------------------------------------------------------------------------

class TestConfigCommand:
    def test_shows_no_config_message_when_empty(self, tmp_config: Path) -> None:
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "Belum ada konfigurasi" in result.output

    def test_shows_table_when_config_exists(self, tmp_config: Path) -> None:
        _write_config(
            tmp_config,
            {"base_url": "http://localhost:8000", "username": "alice", "token": "tok123"},
        )
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "http://localhost:8000" in result.output
        assert "alice" in result.output


# ---------------------------------------------------------------------------
# Command: login
# ---------------------------------------------------------------------------

class TestLoginCommand:
    def test_login_success_saves_token(self, tmp_config: Path) -> None:
        mock_resp = _mock_response(200, {"data": {"access_token": "jwt_token_abc"}})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["login", "--url", "http://localhost:8000", "--username", "alice", "--password", "pass"],
            )
        assert result.exit_code == 0
        assert "Login berhasil" in result.output
        cfg = _load_config()
        assert cfg["token"] == "jwt_token_abc"
        assert cfg["username"] == "alice"
        assert cfg["base_url"] == "http://localhost:8000"

    def test_login_trims_trailing_slash_from_url(self, tmp_config: Path) -> None:
        mock_resp = _mock_response(200, {"data": {"access_token": "tok"}})
        with patch("app.cli._request", return_value=mock_resp):
            runner.invoke(
                app,
                ["login", "--url", "http://localhost:8000/", "--username", "u", "--password", "p"],
            )
        assert _load_config()["base_url"] == "http://localhost:8000"

    def test_login_401_prints_error_and_exits(self, tmp_config: Path) -> None:
        mock_resp = _mock_response(401, {"detail": "Unauthorized"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["login", "--url", "http://localhost:8000", "--username", "x", "--password", "wrong"],
            )
        assert result.exit_code == 1
        assert "salah" in result.output

    def test_login_500_prints_error_and_exits(self, tmp_config: Path) -> None:
        mock_resp = _mock_response(500, {"detail": "Internal Server Error"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["login", "--url", "http://localhost:8000", "--username", "u", "--password", "p"],
            )
        assert result.exit_code == 1

    def test_login_missing_token_in_response(self, tmp_config: Path) -> None:
        mock_resp = _mock_response(200, {"data": {}})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["login", "--url", "http://localhost:8000", "--username", "u", "--password", "p"],
            )
        assert result.exit_code == 1
        assert "token tidak ditemukan" in result.output

    def test_login_connect_error_exits(self, tmp_config: Path) -> None:
        with patch(
            "app.cli._request",
            side_effect=SystemExit(1),
        ):
            result = runner.invoke(
                app,
                ["login", "--url", "http://dead:9999", "--username", "u", "--password", "p"],
            )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Command: logout
# ---------------------------------------------------------------------------

class TestLogoutCommand:
    def test_logout_removes_token(self, tmp_config: Path) -> None:
        _write_config(tmp_config, {"base_url": "http://x", "token": "abc", "username": "u"})
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "Logout berhasil" in result.output
        assert "token" not in _load_config()

    def test_logout_when_already_logged_out(self, tmp_config: Path) -> None:
        _write_config(tmp_config, {"base_url": "http://x"})
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "kondisi logout" in result.output


# ---------------------------------------------------------------------------
# Command: deploy
# ---------------------------------------------------------------------------

class TestDeployCommand:
    def _with_auth_config(self, tmp_config: Path) -> None:
        _write_config(
            tmp_config,
            {"base_url": "http://localhost:8000", "token": "valid_token"},
        )

    def test_deploy_success(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(
            201,
            {
                "data": {
                    "id": 10,
                    "status": "success",
                    "branch": "main",
                    "application_id": 42,
                    "server_id": 1,
                }
            },
        )
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["deploy", "42", "--server-id", "1"])
        assert result.exit_code == 0
        assert "Deployment berhasil dipicu" in result.output
        assert "10" in result.output

    def test_deploy_with_branch_override(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(
            201,
            {"data": {"id": 11, "status": "deploying", "branch": "feature/x"}},
        )
        captured_payload: list[dict] = []  # type: ignore[type-arg]

        def capture_request(method: str, url: str, **kwargs: object) -> MagicMock:
            captured_payload.append(kwargs.get("json_body", {}))  # type: ignore[arg-type]
            return mock_resp

        with patch("app.cli._request", side_effect=capture_request):
            result = runner.invoke(
                app, ["deploy", "42", "--server-id", "1", "--branch", "feature/x"]
            )
        assert result.exit_code == 0
        assert captured_payload[0].get("branch") == "feature/x"

    def test_deploy_404_not_found(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(404, {"detail": "Not found"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["deploy", "99", "--server-id", "1"])
        assert result.exit_code == 1
        assert "tidak ditemukan" in result.output

    def test_deploy_401_unauthorized(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(401, {"detail": "Unauthorized"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["deploy", "42", "--server-id", "1"])
        assert result.exit_code == 1
        assert "terautentikasi" in result.output

    def test_deploy_500_server_error(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(500, {"detail": "Internal Error"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["deploy", "42", "--server-id", "1"])
        assert result.exit_code == 1

    def test_deploy_no_token_exits(self, tmp_config: Path) -> None:
        _write_config(tmp_config, {"base_url": "http://localhost:8000"})
        result = runner.invoke(app, ["deploy", "42", "--server-id", "1"])
        assert result.exit_code == 1

    def test_deploy_no_base_url_exits(self, tmp_config: Path) -> None:
        result = runner.invoke(app, ["deploy", "42", "--server-id", "1"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Command: status
# ---------------------------------------------------------------------------

class TestStatusCommand:
    def _with_auth_config(self, tmp_config: Path) -> None:
        _write_config(
            tmp_config,
            {"base_url": "http://localhost:8000", "token": "valid_token"},
        )

    def test_status_success_shows_table(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(
            200,
            {
                "data": {
                    "id": 10,
                    "application_id": 5,
                    "server_id": 1,
                    "status": "success",
                    "branch": "main",
                    "commit_sha": "deadbeef",
                    "started_at": "2026-08-04T12:00:00Z",
                    "finished_at": "2026-08-04T12:01:00Z",
                    "duration": 60.0,
                }
            },
        )
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["status", "10"])
        assert result.exit_code == 0
        assert "success" in result.output
        assert "deadbeef" in result.output
        assert "main" in result.output

    def test_status_deploying_shows_running(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(
            200,
            {
                "data": {
                    "id": 11,
                    "application_id": 5,
                    "server_id": 1,
                    "status": "deploying",
                    "branch": "main",
                    "commit_sha": None,
                    "started_at": "2026-08-04T12:00:00Z",
                    "finished_at": None,
                    "duration": None,
                }
            },
        )
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["status", "11"])
        assert result.exit_code == 0
        assert "deploying" in result.output
        assert "sedang berjalan" in result.output

    def test_status_404_not_found(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(404, {"detail": "Not found"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["status", "99"])
        assert result.exit_code == 1
        assert "tidak ditemukan" in result.output

    def test_status_401_unauthorized(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(401, {"detail": "Unauthorized"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["status", "10"])
        assert result.exit_code == 1
        assert "terautentikasi" in result.output

    def test_status_500_server_error(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(500, {"detail": "Internal Error"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["status", "10"])
        assert result.exit_code == 1

    def test_status_no_token_exits(self, tmp_config: Path) -> None:
        _write_config(tmp_config, {"base_url": "http://localhost:8000"})
        result = runner.invoke(app, ["status", "10"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Command: logs
# ---------------------------------------------------------------------------

class TestLogsCommand:
    def _with_auth_config(self, tmp_config: Path) -> None:
        _write_config(
            tmp_config,
            {"base_url": "http://localhost:8000", "token": "valid_token"},
        )

    def _dep_response(self, log_path: str | None = None, status: str = "success") -> MagicMock:
        return _mock_response(
            200,
            {
                "data": {
                    "id": 10,
                    "status": status,
                    "log_path": log_path,
                    "branch": "main",
                }
            },
        )

    def test_logs_shows_file_content(
        self, tmp_config: Path, tmp_path: Path
    ) -> None:
        self._with_auth_config(tmp_config)
        log_file = tmp_path / "deploy.log"
        log_file.write_text(
            "[InfraForge] Start\n[InfraForge] Done\n", encoding="utf-8"
        )
        mock_resp = self._dep_response(log_path=str(log_file))
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10"])
        assert result.exit_code == 0
        assert "[InfraForge] Start" in result.output
        assert "[InfraForge] Done" in result.output

    def test_logs_tail_limits_output(
        self, tmp_config: Path, tmp_path: Path
    ) -> None:
        self._with_auth_config(tmp_config)
        log_file = tmp_path / "deploy.log"
        lines = [f"line {i}\n" for i in range(20)]
        log_file.write_text("".join(lines))
        mock_resp = self._dep_response(log_path=str(log_file))
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10", "--tail", "5"])
        assert result.exit_code == 0
        assert "line 19" in result.output
        assert "line 0" not in result.output

    def test_logs_tail_zero_shows_all(
        self, tmp_config: Path, tmp_path: Path
    ) -> None:
        self._with_auth_config(tmp_config)
        log_file = tmp_path / "deploy.log"
        lines = [f"line {i}\n" for i in range(10)]
        log_file.write_text("".join(lines))
        mock_resp = self._dep_response(log_path=str(log_file))
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10", "--tail", "0"])
        assert result.exit_code == 0
        assert "line 0" in result.output
        assert "line 9" in result.output

    def test_logs_no_log_path_shows_message(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = self._dep_response(log_path=None, status="pending")
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10"])
        assert result.exit_code == 0
        assert "belum memiliki log file" in result.output

    def test_logs_file_missing_exits(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = self._dep_response(log_path="/tmp/nonexistent_deploy_99999.log")
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10"])
        assert result.exit_code == 1
        assert "tidak ditemukan" in result.output

    def test_logs_404_deployment_not_found(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(404, {"detail": "Not found"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "99"])
        assert result.exit_code == 1
        assert "tidak ditemukan" in result.output

    def test_logs_401_unauthorized(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(401, {"detail": "Unauthorized"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10"])
        assert result.exit_code == 1
        assert "terautentikasi" in result.output

    def test_logs_500_server_error(self, tmp_config: Path) -> None:
        self._with_auth_config(tmp_config)
        mock_resp = _mock_response(500, {"detail": "error"})
        with patch("app.cli._request", return_value=mock_resp):
            result = runner.invoke(app, ["logs", "10"])
        assert result.exit_code == 1

    def test_logs_no_token_exits(self, tmp_config: Path) -> None:
        _write_config(tmp_config, {"base_url": "http://localhost:8000"})
        result = runner.invoke(app, ["logs", "10"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# CLI entrypoint: --help
# ---------------------------------------------------------------------------

class TestCLIHelp:
    def test_root_help_lists_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        out = _strip_ansi(result.output)
        assert "login" in out
        assert "deploy" in out
        assert "status" in out
        assert "logs" in out

    def test_deploy_help_shows_options(self) -> None:
        result = runner.invoke(app, ["deploy", "--help"])
        assert result.exit_code == 0
        out = _strip_ansi(result.output)
        assert "--server-id" in out
        assert "--branch" in out

    def test_logs_help_shows_tail_option(self) -> None:
        result = runner.invoke(app, ["logs", "--help"])
        assert result.exit_code == 0
        out = _strip_ansi(result.output)
        assert "--tail" in out
