from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.server import AuthType, ServerStatus


class ServerCreate(BaseModel):
    """Payload untuk menambahkan server baru."""

    name: str = Field(min_length=1, max_length=100, description="Nama server (label tampilan)")
    host: str = Field(min_length=1, max_length=253, description="IP address atau hostname")
    port: int = Field(default=22, ge=1, le=65535, description="Port SSH (default 22)")
    username: str = Field(min_length=1, max_length=100, description="SSH username")
    auth_type: AuthType = Field(description="Metode autentikasi: password atau private_key")
    password: str | None = Field(default=None, description="Password SSH (wajib jika auth_type=password)")
    private_key: str | None = Field(default=None, description="Isi private key SSH (wajib jika auth_type=private_key)")

    @model_validator(mode="after")
    def validate_auth_credentials(self) -> "ServerCreate":
        if self.auth_type == AuthType.password and not self.password:
            raise ValueError("password wajib diisi jika auth_type adalah 'password'")
        if self.auth_type == AuthType.private_key and not self.private_key:
            raise ValueError("private_key wajib diisi jika auth_type adalah 'private_key'")
        return self


class ServerUpdate(BaseModel):
    """Payload PATCH — semua field opsional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=100)
    auth_type: AuthType | None = None
    password: str | None = None
    private_key: str | None = None
    status: ServerStatus | None = None


class ServerResponse(BaseModel):
    """Response publik — tidak mengekspos password/private_key."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    host: str
    port: int
    username: str
    auth_type: AuthType
    status: ServerStatus
    created_at: datetime
    updated_at: datetime


class SSHTestResult(BaseModel):
    """Hasil tes koneksi SSH."""

    server_id: int
    host: str
    port: int
    success: bool
    message: str
