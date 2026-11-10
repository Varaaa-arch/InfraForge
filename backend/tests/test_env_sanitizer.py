"""
Tests untuk sanitasi environment variables (P0 Item #5).

Coverage:
  - sanitize_env_value_input: reject newline/null, strip whitespace, valid values
  - sanitize_env_key_input: normalisasi uppercase, reject format invalid
  - sanitize_env_value_output: strip control chars, quoting, escaping
  - build_env_file_line: format output baris .env
  - EnvVarCreate schema: field_validator menerima/reject value
  - _write_env_file: output file .env berisi value yang sudah disanitasi
  - API endpoint: POST /projects/{id}/env reject value dengan newline
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from app.utils.env_sanitizer import (
    build_env_file_line,
    sanitize_env_key_input,
    sanitize_env_value_input,
    sanitize_env_value_output,
)


# ---------------------------------------------------------------------------
# sanitize_env_value_input
# ---------------------------------------------------------------------------

class TestSanitizeEnvValueInput:
    def test_valid_simple_value(self) -> None:
        assert sanitize_env_value_input("hello") == "hello"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert sanitize_env_value_input("  hello  ") == "hello"

    def test_valid_url_value(self) -> None:
        url = "postgres://user:pass@localhost:5432/db"
        assert sanitize_env_value_input(url) == url

    def test_valid_value_with_special_chars(self) -> None:
        val = "P@ssw0rd!#$%^&*()"
        assert sanitize_env_value_input(val) == val

    def test_rejects_newline_lf(self) -> None:
        with pytest.raises(ValueError, match=r"karakter yang tidak diizinkan"):
            sanitize_env_value_input("value\nINJECTED=evil")

    def test_rejects_newline_cr(self) -> None:
        with pytest.raises(ValueError, match=r"karakter yang tidak diizinkan"):
            sanitize_env_value_input("value\rINJECTED=evil")

    def test_rejects_null_byte(self) -> None:
        with pytest.raises(ValueError, match=r"karakter yang tidak diizinkan"):
            sanitize_env_value_input("value\x00injected")

    def test_rejects_embedded_newline_in_middle(self) -> None:
        with pytest.raises(ValueError):
            sanitize_env_value_input("line1\nline2")

    def test_rejects_crlf(self) -> None:
        with pytest.raises(ValueError):
            sanitize_env_value_input("value\r\nINJECTED=evil")

    def test_valid_value_with_tabs(self) -> None:
        val = "value\twith\ttabs"
        assert sanitize_env_value_input(val) == val

    def test_valid_multiword_no_newline(self) -> None:
        val = "this is a secret value"
        assert sanitize_env_value_input(val) == val


# ---------------------------------------------------------------------------
# sanitize_env_key_input
# ---------------------------------------------------------------------------

class TestSanitizeEnvKeyInput:
    def test_valid_key_uppercase(self) -> None:
        assert sanitize_env_key_input("DATABASE_URL") == "DATABASE_URL"

    def test_lowercase_key_normalized_to_upper(self) -> None:
        assert sanitize_env_key_input("database_url") == "DATABASE_URL"

    def test_mixed_case_normalized(self) -> None:
        assert sanitize_env_key_input("MyKey") == "MYKEY"

    def test_strips_whitespace(self) -> None:
        assert sanitize_env_key_input("  KEY  ") == "KEY"

    def test_key_with_underscore(self) -> None:
        assert sanitize_env_key_input("MY_SECRET_KEY") == "MY_SECRET_KEY"

    def test_key_starting_with_underscore(self) -> None:
        assert sanitize_env_key_input("_PRIVATE") == "_PRIVATE"

    def test_rejects_key_starting_with_digit(self) -> None:
        with pytest.raises(ValueError, match="tidak valid"):
            sanitize_env_key_input("1INVALID")

    def test_rejects_key_with_hyphen(self) -> None:
        with pytest.raises(ValueError):
            sanitize_env_key_input("MY-KEY")

    def test_rejects_key_with_space(self) -> None:
        with pytest.raises(ValueError):
            sanitize_env_key_input("MY KEY")

    def test_rejects_empty_key(self) -> None:
        with pytest.raises(ValueError, match="kosong"):
            sanitize_env_key_input("")

    def test_rejects_whitespace_only_key(self) -> None:
        with pytest.raises(ValueError, match="kosong"):
            sanitize_env_key_input("   ")


# ---------------------------------------------------------------------------
# sanitize_env_value_output
# ---------------------------------------------------------------------------

class TestSanitizeEnvValueOutput:
    def test_simple_value_no_quoting_needed(self) -> None:
        assert sanitize_env_value_output("simple") == "simple"

    def test_alphanumeric_no_quoting(self) -> None:
        assert sanitize_env_value_output("abc123") == "abc123"

    def test_value_with_space_gets_quoted(self) -> None:
        assert sanitize_env_value_output("hello world") == '"hello world"'

    def test_value_with_hash_gets_quoted(self) -> None:
        result = sanitize_env_value_output("value#comment")
        assert result.startswith('"') and result.endswith('"')

    def test_value_with_dollar_gets_quoted(self) -> None:
        result = sanitize_env_value_output("$MY_VAR")
        assert result.startswith('"') and result.endswith('"')

    def test_value_with_backtick_gets_quoted(self) -> None:
        result = sanitize_env_value_output("`command`")
        assert result.startswith('"') and result.endswith('"')

    def test_embedded_double_quote_escaped(self) -> None:
        result = sanitize_env_value_output('say "hello"')
        assert '\\"' in result
        assert result.startswith('"') and result.endswith('"')

    def test_embedded_backslash_escaped(self) -> None:
        result = sanitize_env_value_output("path\\to\\file")
        assert "\\\\" in result

    def test_newline_stripped_defense_in_depth(self) -> None:
        result = sanitize_env_value_output("line1\nline2")
        assert "\n" not in result

    def test_null_byte_stripped(self) -> None:
        result = sanitize_env_value_output("value\x00injected")
        assert "\x00" not in result

    def test_control_chars_stripped(self) -> None:
        result = sanitize_env_value_output("value\x01\x02\x1f")
        assert "\x01" not in result
        assert "\x1f" not in result

    def test_empty_after_sanitize_returns_empty_quoted(self) -> None:
        result = sanitize_env_value_output("\x00\x01\x02")
        assert result == '""'

    def test_url_no_quoting_needed(self) -> None:
        url = "https://example.com/path"
        assert sanitize_env_value_output(url) == url


# ---------------------------------------------------------------------------
# build_env_file_line
# ---------------------------------------------------------------------------

class TestBuildEnvFileLine:
    def test_simple_line(self) -> None:
        assert build_env_file_line("DB_HOST", "localhost") == "DB_HOST=localhost\n"

    def test_value_with_spaces_quoted(self) -> None:
        assert build_env_file_line("APP_NAME", "My App") == 'APP_NAME="My App"\n'

    def test_key_normalized_to_uppercase(self) -> None:
        line = build_env_file_line("db_host", "localhost")
        assert line.startswith("DB_HOST=")

    def test_line_ends_with_newline(self) -> None:
        line = build_env_file_line("KEY", "value")
        assert line.endswith("\n")

    def test_newline_in_value_stripped_at_output(self) -> None:
        # Output layer: newline di-strip, seluruh konten jadi satu value
        # Key "INJECTED" tidak boleh muncul sebagai baris terpisah
        line = build_env_file_line("KEY", "val\nINJECTED=evil")
        # Hanya boleh ada satu baris (KEY=...) — tidak ada baris kedua
        assert line.count("\n") == 1  # hanya newline penutup
        assert line.startswith("KEY=")

    def test_null_byte_stripped_at_output(self) -> None:
        line = build_env_file_line("KEY", "val\x00injected")
        assert "\x00" not in line

    def test_invalid_key_raises(self) -> None:
        with pytest.raises(ValueError):
            build_env_file_line("1INVALID", "value")


# ---------------------------------------------------------------------------
# Integration: _write_env_file
# ---------------------------------------------------------------------------

class TestWriteEnvFile:
    def test_output_contains_sanitized_lines(self) -> None:
        from app.services.deployment_service import _write_env_file

        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(Path(tmp), {
                "DB_HOST": "localhost",
                "APP_NAME": "My App",
                "SECRET": "P@ss#word",
            })
            content = env_file.read_text(encoding="utf-8")

        assert "DB_HOST=localhost\n" in content
        assert 'APP_NAME="My App"\n' in content
        assert "SECRET=" in content

    def test_newline_injection_prevented(self) -> None:
        from app.services.deployment_service import _write_env_file

        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(Path(tmp), {"KEY": "value\nINJECTED=evil"})
            content = env_file.read_text(encoding="utf-8")

        lines = [l for l in content.splitlines() if l.strip()]
        keys = [l.split("=")[0] for l in lines if "=" in l]
        assert "INJECTED" not in keys

    def test_null_byte_stripped(self) -> None:
        from app.services.deployment_service import _write_env_file

        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(Path(tmp), {"KEY": "val\x00ue"})
            content = env_file.read_text(encoding="utf-8")

        assert "\x00" not in content

    def test_multiple_vars_all_written(self) -> None:
        from app.services.deployment_service import _write_env_file

        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(Path(tmp), {
                "HOST": "localhost",
                "PORT": "5432",
                "USER": "admin",
            })
            content = env_file.read_text(encoding="utf-8")

        assert "HOST=localhost" in content
        assert "PORT=5432" in content
        assert "USER=admin" in content
        assert len(content.splitlines()) == 3

    def test_empty_dict_creates_empty_file(self) -> None:
        from app.services.deployment_service import _write_env_file

        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(Path(tmp), {})
            content = env_file.read_text(encoding="utf-8")

        assert content == ""


# ---------------------------------------------------------------------------
# Integration: API endpoint
# ---------------------------------------------------------------------------

class TestEnvVarApiSanitization:
    def _setup(self, client) -> tuple[dict, int]:
        suffix = uuid.uuid4().hex[:8]
        user = {"username": f"san_{suffix}", "email": f"san_{suffix}@t.com", "password": "pass1234"}
        client.post("/auth/register", json=user)
        r = client.post("/auth/login", data={"username": user["username"], "password": user["password"]})
        token = r.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        proj = client.post("/projects", json={"name": f"p-{uuid.uuid4().hex[:6]}", "description": "t"}, headers=headers)
        return headers, int(proj.json()["data"]["id"])

    def test_valid_env_var_accepted(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "DB_HOST", "value": "localhost"}]}, headers=headers)
        assert r.status_code == 200

    def test_newline_lf_rejected(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "KEY", "value": "val\nINJECTED=evil"}]}, headers=headers)
        assert r.status_code == 422

    def test_newline_cr_rejected(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "KEY", "value": "val\rinjected"}]}, headers=headers)
        assert r.status_code == 422

    def test_null_byte_rejected(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "KEY", "value": "val\x00ue"}]}, headers=headers)
        assert r.status_code == 422

    def test_crlf_rejected(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "KEY", "value": "val\r\nINJECTED=evil"}]}, headers=headers)
        assert r.status_code == 422

    def test_special_chars_accepted(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "SECRET", "value": "P@ss#w0rd!$^&*()"}]}, headers=headers)
        assert r.status_code == 200

    def test_whitespace_stripped_accepted(self, client) -> None:
        headers, pid = self._setup(client)
        r = client.post(f"/projects/{pid}/env",
            json={"env_vars": [{"key": "KEY", "value": "  value  "}]}, headers=headers)
        assert r.status_code == 200
