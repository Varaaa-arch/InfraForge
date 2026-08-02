"""
Unit test untuk Task 3.11 — Environment Variables dengan enkripsi Fernet.

Coverage:
1. EncryptionService  — encrypt/decrypt roundtrip, idempotency, invalid token
2. Schema validation  — key format, uppercase normalisasi, bulk validation
3. Masking helper     — format masked value
4. CRUD endpoints     — POST bulk upsert, GET list, GET detail, DELETE
5. Authorization      — 401 tanpa token, 404 project milik orang lain
6. Upsert semantics   — key yang sama di-update bukan di-insert ulang
"""

import uuid

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_user() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "username": f"user_{suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "password123",
    }


def _register_and_login(client: TestClient, payload: dict[str, str]) -> dict[str, str]:
    client.post("/auth/register", json=payload)
    r = client.post(
        "/auth/login",
        data={"username": payload["username"], "password": payload["password"]},
    )
    return dict(r.json()["data"])


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _create_project(client: TestClient, tokens: dict[str, str], name: str = "test-project") -> dict:
    r = client.post("/projects", headers=_auth(tokens), json={"name": name})
    assert r.status_code == 201
    return dict(r.json()["data"])


def _env_url(project_id: int) -> str:
    return f"/projects/{project_id}/env"


# ---------------------------------------------------------------------------
# 1. Encryption Service — pure unit tests (tanpa DB / HTTP)
# ---------------------------------------------------------------------------

class TestEncryptionService:
    def test_encrypt_returns_non_empty_string(self) -> None:
        from app.services.encryption_service import encrypt
        ct = encrypt("hello world")
        assert isinstance(ct, str)
        assert len(ct) > 0

    def test_encrypt_does_not_equal_plaintext(self) -> None:
        from app.services.encryption_service import encrypt
        plaintext = "super-secret-value"
        assert encrypt(plaintext) != plaintext

    def test_decrypt_roundtrip(self) -> None:
        from app.services.encryption_service import decrypt, encrypt
        plaintext = "DATABASE_URL=postgres://user:pass@localhost/db"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_two_encryptions_produce_different_ciphertext(self) -> None:
        """Fernet menggunakan random IV — setiap enkripsi menghasilkan ciphertext berbeda."""
        from app.services.encryption_service import encrypt
        val = "same-value"
        assert encrypt(val) != encrypt(val)

    def test_decrypt_invalid_token_raises_value_error(self) -> None:
        from app.services.encryption_service import decrypt
        with pytest.raises(ValueError, match="Dekripsi gagal"):
            decrypt("not-a-valid-fernet-token")

    def test_decrypt_tampered_ciphertext_raises_value_error(self) -> None:
        from app.services.encryption_service import decrypt, encrypt
        ct = encrypt("original")
        # Ubah satu karakter di tengah ciphertext
        tampered = ct[:-5] + "XXXXX"
        with pytest.raises(ValueError):
            decrypt(tampered)

    def test_encrypt_decrypt_unicode(self) -> None:
        from app.services.encryption_service import decrypt, encrypt
        plaintext = "密码=こんにちは🔑"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_encrypt_decrypt_empty_like_string(self) -> None:
        """Nilai kosong tidak boleh lolos schema, tapi service sendiri tetap bisa enkripsinya."""
        from app.services.encryption_service import decrypt, encrypt
        # Spasi tunggal adalah string valid dari sudut pandang Fernet
        assert decrypt(encrypt(" ")) == " "

    def test_rotate_key(self) -> None:
        """Setelah rotate_key, ciphertext baru bisa didekripsi dengan kunci baru."""
        import base64
        import hashlib

        from cryptography.fernet import Fernet

        from app.services.encryption_service import decrypt, encrypt, rotate_key

        original = "jwt-secret-value-xyz"
        old_ct = encrypt(original)

        # Buat kunci baru yang berbeda
        new_raw = "totally-different-new-key-for-rotation"
        new_digest = hashlib.sha256(new_raw.encode()).digest()
        new_fernet_key = base64.urlsafe_b64encode(new_digest)
        new_fernet = Fernet(new_fernet_key)

        new_ct = rotate_key(old_ct, new_fernet)

        # Kunci baru bisa dekripsi
        assert new_fernet.decrypt(new_ct.encode()).decode() == original
        # Kunci lama (default) tidak bisa dekripsi ciphertext baru
        with pytest.raises(ValueError):
            decrypt(new_ct)


# ---------------------------------------------------------------------------
# 2. Schema validation — tanpa DB / HTTP
# ---------------------------------------------------------------------------

class TestEnvVarSchemas:
    def test_key_normalized_to_uppercase(self) -> None:
        from app.schemas.env_var import EnvVarCreate
        ev = EnvVarCreate(key="database_url", value="postgres://")
        assert ev.key == "DATABASE_URL"

    def test_key_already_uppercase_accepted(self) -> None:
        from app.schemas.env_var import EnvVarCreate
        ev = EnvVarCreate(key="JWT_SECRET", value="s3cr3t")
        assert ev.key == "JWT_SECRET"

    def test_key_with_number_suffix_accepted(self) -> None:
        from app.schemas.env_var import EnvVarCreate
        ev = EnvVarCreate(key="VAR_2", value="val")
        assert ev.key == "VAR_2"

    def test_key_starting_with_number_rejected(self) -> None:
        from pydantic import ValidationError
        from app.schemas.env_var import EnvVarCreate
        with pytest.raises(ValidationError, match="key hanya boleh"):
            EnvVarCreate(key="1INVALID", value="val")

    def test_key_with_hyphen_rejected(self) -> None:
        from pydantic import ValidationError
        from app.schemas.env_var import EnvVarCreate
        with pytest.raises(ValidationError, match="key hanya boleh"):
            EnvVarCreate(key="INVALID-KEY", value="val")

    def test_key_with_space_rejected(self) -> None:
        from pydantic import ValidationError
        from app.schemas.env_var import EnvVarCreate
        with pytest.raises(ValidationError):
            EnvVarCreate(key="INVA LID", value="val")

    def test_empty_value_rejected(self) -> None:
        from pydantic import ValidationError
        from app.schemas.env_var import EnvVarCreate
        with pytest.raises(ValidationError):
            EnvVarCreate(key="KEY", value="")

    def test_bulk_create_empty_list_rejected(self) -> None:
        from pydantic import ValidationError
        from app.schemas.env_var import EnvVarBulkCreate
        with pytest.raises(ValidationError):
            EnvVarBulkCreate(env_vars=[])

    def test_masked_response_has_no_plaintext_value_field(self) -> None:
        from app.schemas.env_var import EnvVarMaskedResponse
        fields = EnvVarMaskedResponse.model_fields
        assert "value" not in fields
        assert "masked_value" in fields


# ---------------------------------------------------------------------------
# 3. Masking helper — tanpa DB / HTTP
# ---------------------------------------------------------------------------

class TestMaskValue:
    def _mask(self, s: str) -> str:
        from app.services.env_var_service import _mask_value  # type: ignore[attr-defined]
        return _mask_value(s)

    def test_long_value_shows_first_3_chars(self) -> None:
        assert self._mask("postgres://user:pass@host/db").startswith("pos")
        assert self._mask("postgres://user:pass@host/db").endswith("****")

    def test_short_value_fully_masked(self) -> None:
        assert self._mask("ab") == "****"

    def test_3_char_value_shows_all_3(self) -> None:
        result = self._mask("abc")
        assert result == "abc****"

    def test_mask_always_ends_with_4_stars(self) -> None:
        for val in ["x", "xy", "xyz", "abcdefgh"]:
            assert self._mask(val).endswith("****")


# ---------------------------------------------------------------------------
# 4. CRUD Endpoint tests
# ---------------------------------------------------------------------------

class TestEnvVarCRUD:
    def test_bulk_upsert_creates_new_vars(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={
                "env_vars": [
                    {"key": "DATABASE_URL", "value": "postgres://localhost/db"},
                    {"key": "JWT_SECRET", "value": "supersecret"},
                ]
            },
        )
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["summary"]["created"] == 2
        assert body["summary"]["updated"] == 0
        assert body["summary"]["total"] == 2
        keys = [ev["key"] for ev in body["env_vars"]]
        assert "DATABASE_URL" in keys
        assert "JWT_SECRET" in keys

    def test_bulk_upsert_normalizes_key_to_uppercase(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "my_db_url", "value": "postgres://"}]},
        )
        assert r.status_code == 200
        key = r.json()["data"]["env_vars"][0]["key"]
        assert key == "MY_DB_URL"

    def test_bulk_upsert_updates_existing_key(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        # Insert pertama
        client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "API_KEY", "value": "old-value"}]},
        )

        # Upsert dengan value baru
        r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "API_KEY", "value": "new-value"}]},
        )
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["summary"]["created"] == 0
        assert body["summary"]["updated"] == 1
        assert body["env_vars"][0]["value"] == "new-value"

    def test_bulk_upsert_no_duplicate_key_in_db(self, client: TestClient) -> None:
        """Setelah dua upsert dengan key sama, hanya ada satu baris di DB."""
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        for _ in range(3):
            client.post(
                _env_url(pid),
                headers=_auth(tokens),
                json={"env_vars": [{"key": "UNIQUE_KEY", "value": "val"}]},
            )

        r = client.get(_env_url(pid), headers=_auth(tokens))
        env_keys = [ev["key"] for ev in r.json()["data"]]
        assert env_keys.count("UNIQUE_KEY") == 1

    def test_list_env_vars_returns_masked_values(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "SECRET_TOKEN", "value": "abcdefgh"}]},
        )

        r = client.get(_env_url(pid), headers=_auth(tokens))
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        item = data[0]
        # Value harus disamarkan — tidak boleh menampilkan value asli
        assert "masked_value" in item
        assert "value" not in item
        assert item["masked_value"] == "abc****"

    def test_list_env_vars_sorted_alphabetically(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={
                "env_vars": [
                    {"key": "ZEBRA", "value": "z"},
                    {"key": "ALPHA", "value": "a"},
                    {"key": "MIDDLE", "value": "m"},
                ]
            },
        )

        r = client.get(_env_url(pid), headers=_auth(tokens))
        keys = [ev["key"] for ev in r.json()["data"]]
        assert keys == sorted(keys)

    def test_get_env_var_detail_returns_plaintext(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        create_r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "REDIS_URL", "value": "redis://localhost:6379"}]},
        )
        env_id = create_r.json()["data"]["env_vars"][0]["id"]

        r = client.get(f"{_env_url(pid)}/{env_id}", headers=_auth(tokens))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["key"] == "REDIS_URL"
        assert data["value"] == "redis://localhost:6379"  # plaintext, bukan ciphertext

    def test_get_env_var_detail_not_found(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        r = client.get(f"{_env_url(pid)}/99999999", headers=_auth(tokens))
        assert r.status_code == 404

    def test_delete_env_var(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        create_r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "TO_DELETE", "value": "bye"}]},
        )
        env_id = create_r.json()["data"]["env_vars"][0]["id"]

        r = client.delete(f"{_env_url(pid)}/{env_id}", headers=_auth(tokens))
        assert r.status_code == 200
        assert "deleted" in r.json()["data"]["message"].lower()

        # Setelah hapus, list harus kosong
        list_r = client.get(_env_url(pid), headers=_auth(tokens))
        assert list_r.json()["data"] == []

    def test_delete_env_var_not_found(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        r = client.delete(f"{_env_url(pid)}/99999999", headers=_auth(tokens))
        assert r.status_code == 404

    def test_env_vars_isolated_per_project(self, client: TestClient) -> None:
        """Env vars satu project tidak boleh muncul di project lain."""
        tokens = _register_and_login(client, _unique_user())
        proj_a = _create_project(client, tokens, "project-alpha")
        proj_b = _create_project(client, tokens, "project-beta")

        client.post(
            _env_url(proj_a["id"]),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "ONLY_IN_A", "value": "val"}]},
        )

        r = client.get(_env_url(proj_b["id"]), headers=_auth(tokens))
        keys = [ev["key"] for ev in r.json()["data"]]
        assert "ONLY_IN_A" not in keys

    def test_invalid_key_format_returns_422(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": [{"key": "INVALID-KEY", "value": "val"}]},
        )
        assert r.status_code == 422

    def test_empty_env_vars_list_returns_422(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        project = _create_project(client, tokens)
        pid = project["id"]

        r = client.post(
            _env_url(pid),
            headers=_auth(tokens),
            json={"env_vars": []},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 5. Authorization tests
# ---------------------------------------------------------------------------

class TestEnvVarAuthorization:
    def test_post_without_token_returns_401(self, client: TestClient) -> None:
        r = client.post(
            "/projects/1/env",
            json={"env_vars": [{"key": "KEY", "value": "val"}]},
        )
        assert r.status_code == 401

    def test_get_without_token_returns_401(self, client: TestClient) -> None:
        r = client.get("/projects/1/env")
        assert r.status_code == 401

    def test_delete_without_token_returns_401(self, client: TestClient) -> None:
        r = client.delete("/projects/1/env/1")
        assert r.status_code == 401

    def test_access_other_users_project_returns_404(self, client: TestClient) -> None:
        """User B tidak boleh mengakses env vars project milik User A."""
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())

        project_a = _create_project(client, tokens_a, "user-a-project")
        pid_a = project_a["id"]

        # User A buat env var
        client.post(
            _env_url(pid_a),
            headers=_auth(tokens_a),
            json={"env_vars": [{"key": "SECRET", "value": "private"}]},
        )

        # User B coba list env vars project A → harus 404
        r = client.get(_env_url(pid_a), headers=_auth(tokens_b))
        assert r.status_code == 404

    def test_upsert_to_other_users_project_returns_404(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())

        project_a = _create_project(client, tokens_a, "proj-a")
        pid_a = project_a["id"]

        r = client.post(
            _env_url(pid_a),
            headers=_auth(tokens_b),
            json={"env_vars": [{"key": "HACK", "value": "attempt"}]},
        )
        assert r.status_code == 404

    def test_delete_from_other_users_project_returns_404(self, client: TestClient) -> None:
        tokens_a = _register_and_login(client, _unique_user())
        tokens_b = _register_and_login(client, _unique_user())

        project_a = _create_project(client, tokens_a, "proj-owned")
        pid_a = project_a["id"]

        create_r = client.post(
            _env_url(pid_a),
            headers=_auth(tokens_a),
            json={"env_vars": [{"key": "VAR_X", "value": "val"}]},
        )
        env_id = create_r.json()["data"]["env_vars"][0]["id"]

        # User B coba hapus env var milik User A → harus 404
        r = client.delete(f"{_env_url(pid_a)}/{env_id}", headers=_auth(tokens_b))
        assert r.status_code == 404

    def test_nonexistent_project_returns_404(self, client: TestClient) -> None:
        tokens = _register_and_login(client, _unique_user())
        r = client.get(_env_url(99999999), headers=_auth(tokens))
        assert r.status_code == 404
