"""
InfraForge CLI — command-line interface untuk berinteraksi dengan InfraForge API.

Commands:
    config          Tampilkan konfigurasi aktif (base URL + status login).
    login           Simpan base URL dan lakukan autentikasi (simpan token JWT).
    logout          Hapus token dari konfigurasi lokal.
    deploy          Picu proses deployment aplikasi ke server.
    status          Cek status / riwayat deployment.
    logs            Tampilkan log deployment.

Konfigurasi disimpan di file JSON di:
    ~/.infraforge/config.json

Contoh penggunaan:
    infraforge-cli login --url http://localhost:8000 --username admin --password secret
    infraforge-cli deploy 42 --server-id 1
    infraforge-cli status 10
    infraforge-cli logs 10
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Konfigurasi lokal
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".infraforge"
CONFIG_FILE = CONFIG_DIR / "config.json"

app = typer.Typer(
    name="infraforge-cli",
    help="InfraForge CLI — kontrol deployments dari terminal.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True, style="bold red")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict[str, Any]:
    """Load konfigurasi dari file JSON lokal."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return dict(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_config(cfg: dict[str, Any]) -> None:
    """Simpan konfigurasi ke file JSON lokal."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _get_base_url(cfg: dict[str, Any]) -> str:
    """Ambil base URL dari config; abort jika belum dikonfigurasi."""
    url = cfg.get("base_url", "")
    if not url:
        err_console.print(
            "Base URL belum dikonfigurasi. Jalankan: infraforge-cli login --url <URL>"
        )
        raise typer.Exit(code=1)
    return str(url)


def _get_token(cfg: dict[str, Any]) -> str:
    """Ambil token dari config; abort jika belum login."""
    token = cfg.get("token", "")
    if not token:
        err_console.print(
            "Belum login. Jalankan: infraforge-cli login --url <URL> --username <user>"
        )
        raise typer.Exit(code=1)
    return str(token)


def _auth_headers(cfg: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_token(cfg)}"}


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    """
    Lakukan HTTP request dan tangani error koneksi secara bersih.
    Raise typer.Exit(1) jika gagal terhubung ke server.
    """
    try:
        resp = httpx.request(
            method,
            url,
            headers=headers,
            json=json_body,
            data=data,
            timeout=30,
        )
        return resp
    except httpx.ConnectError:
        err_console.print(f"Tidak dapat terhubung ke server: {url}")
        raise typer.Exit(code=1)
    except httpx.TimeoutException:
        err_console.print(f"Request timeout ke: {url}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def config() -> None:
    """Tampilkan konfigurasi CLI yang aktif."""
    cfg = _load_config()
    if not cfg:
        console.print("[yellow]Belum ada konfigurasi. Jalankan `login` terlebih dahulu.[/yellow]")
        raise typer.Exit(code=0)

    table = Table(title="InfraForge CLI — Konfigurasi Aktif")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("base_url", cfg.get("base_url", "(belum diset)"))
    table.add_row("username", cfg.get("username", "(belum login)"))
    token = cfg.get("token", "")
    token_display = f"{token[:12]}..." if len(token) > 12 else token or "(belum login)"
    table.add_row("token", token_display)

    console.print(table)


@app.command()
def login(
    url: str = typer.Option(..., "--url", "-u", help="Base URL InfraForge API, e.g. http://localhost:8000"),
    username: str = typer.Option(..., "--username", "-n", help="Username akun InfraForge"),
    password: str = typer.Option(..., "--password", "-p", help="Password akun InfraForge"),
) -> None:
    """Login ke InfraForge API dan simpan token ke konfigurasi lokal."""
    url = url.rstrip("/")

    resp = _request(
        "POST",
        f"{url}/auth/login",
        data={"username": username, "password": password},
    )

    if resp.status_code == 200:
        body = resp.json()
        token = body.get("data", {}).get("access_token", "")
        if not token:
            err_console.print("Login berhasil tapi token tidak ditemukan di respons.")
            raise typer.Exit(code=1)

        cfg = _load_config()
        cfg["base_url"] = url
        cfg["username"] = username
        cfg["token"] = token
        _save_config(cfg)

        console.print(f"[green]Login berhasil sebagai [bold]{username}[/bold]. Token disimpan.[/green]")
    elif resp.status_code == 401:
        err_console.print("Login gagal: username atau password salah.")
        raise typer.Exit(code=1)
    else:
        err_console.print(f"Login gagal: HTTP {resp.status_code} — {resp.text}")
        raise typer.Exit(code=1)


@app.command()
def logout() -> None:
    """Hapus token autentikasi dari konfigurasi lokal."""
    cfg = _load_config()
    if not cfg.get("token"):
        console.print("[yellow]Sudah dalam kondisi logout.[/yellow]")
        raise typer.Exit(code=0)

    cfg.pop("token", None)
    _save_config(cfg)
    console.print("[green]Logout berhasil. Token dihapus dari konfigurasi lokal.[/green]")


@app.command()
def deploy(
    application_id: int = typer.Argument(..., help="ID aplikasi yang akan di-deploy"),
    server_id: int = typer.Option(..., "--server-id", "-s", help="ID server target deployment"),
    branch: str = typer.Option("", "--branch", "-b", help="Branch override (opsional)"),
) -> None:
    """Picu deployment baru untuk aplikasi ke server tertentu."""
    cfg = _load_config()
    base_url = _get_base_url(cfg)
    headers = _auth_headers(cfg)

    payload: dict[str, Any] = {
        "application_id": application_id,
        "server_id": server_id,
    }
    if branch:
        payload["branch"] = branch

    console.print(f"[cyan]Memicu deployment app_id={application_id} → server_id={server_id}...[/cyan]")

    resp = _request("POST", f"{base_url}/deployments", headers=headers, json_body=payload)

    if resp.status_code == 201:
        data = resp.json().get("data", {})
        dep_id = data.get("id")
        status = data.get("status")
        branch_used = data.get("branch")
        console.print(
            f"[green]Deployment berhasil dipicu![/green]\n"
            f"  ID         : {dep_id}\n"
            f"  Status     : {status}\n"
            f"  Branch     : {branch_used}\n"
            f"\nGunakan `infraforge-cli status {dep_id}` untuk memantau."
        )
    elif resp.status_code == 404:
        err_console.print("Application atau server tidak ditemukan.")
        raise typer.Exit(code=1)
    elif resp.status_code == 401:
        err_console.print("Tidak terautentikasi. Jalankan `infraforge-cli login` kembali.")
        raise typer.Exit(code=1)
    else:
        err_console.print(f"Deployment gagal: HTTP {resp.status_code} — {resp.text}")
        raise typer.Exit(code=1)


@app.command()
def status(
    deployment_id: int = typer.Argument(..., help="ID deployment yang ingin dicek"),
) -> None:
    """Cek status deployment berdasarkan ID-nya."""
    cfg = _load_config()
    base_url = _get_base_url(cfg)
    headers = _auth_headers(cfg)

    resp = _request("GET", f"{base_url}/deployments/{deployment_id}", headers=headers)

    if resp.status_code == 200:
        data = resp.json().get("data", {})

        table = Table(title=f"Deployment #{deployment_id}")
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        status_val = str(data.get("status", ""))
        status_color = {
            "success": "green",
            "failed": "red",
            "deploying": "yellow",
            "pending": "blue",
        }.get(status_val, "white")

        table.add_row("ID", str(data.get("id", "")))
        table.add_row("Application ID", str(data.get("application_id", "")))
        table.add_row("Server ID", str(data.get("server_id", "")))
        table.add_row("Status", f"[{status_color}]{status_val}[/{status_color}]")
        table.add_row("Branch", str(data.get("branch", "")))
        table.add_row("Commit SHA", str(data.get("commit_sha") or "(pending)"))
        table.add_row("Started At", str(data.get("started_at", "")))
        table.add_row("Finished At", str(data.get("finished_at") or "(sedang berjalan)"))
        table.add_row("Duration (s)", str(data.get("duration") or "(sedang berjalan)"))

        console.print(table)
    elif resp.status_code == 404:
        err_console.print(f"Deployment #{deployment_id} tidak ditemukan.")
        raise typer.Exit(code=1)
    elif resp.status_code == 401:
        err_console.print("Tidak terautentikasi. Jalankan `infraforge-cli login` kembali.")
        raise typer.Exit(code=1)
    else:
        err_console.print(f"Gagal mengambil status: HTTP {resp.status_code} — {resp.text}")
        raise typer.Exit(code=1)


@app.command()
def logs(
    deployment_id: int = typer.Argument(..., help="ID deployment yang ingin dilihat lognya"),
    tail: int = typer.Option(50, "--tail", "-n", help="Jumlah baris terakhir yang ditampilkan (0 = semua)"),
) -> None:
    """Tampilkan log deployment dari file log yang tersimpan."""
    cfg = _load_config()
    base_url = _get_base_url(cfg)
    headers = _auth_headers(cfg)

    # Ambil info deployment untuk mendapatkan log_path
    resp = _request("GET", f"{base_url}/deployments/{deployment_id}", headers=headers)

    if resp.status_code == 404:
        err_console.print(f"Deployment #{deployment_id} tidak ditemukan.")
        raise typer.Exit(code=1)
    elif resp.status_code == 401:
        err_console.print("Tidak terautentikasi. Jalankan `infraforge-cli login` kembali.")
        raise typer.Exit(code=1)
    elif resp.status_code != 200:
        err_console.print(f"Gagal mengambil deployment: HTTP {resp.status_code}")
        raise typer.Exit(code=1)

    data = resp.json().get("data", {})
    log_path = data.get("log_path")

    if not log_path:
        console.print(
            f"[yellow]Deployment #{deployment_id} belum memiliki log file "
            f"(status: {data.get('status', 'unknown')}).[/yellow]"
        )
        raise typer.Exit(code=0)

    log_file = Path(log_path)
    if not log_file.exists():
        err_console.print(f"File log tidak ditemukan di path: {log_path}")
        raise typer.Exit(code=1)

    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()

    if tail > 0:
        lines = lines[-tail:]

    console.print(
        f"[dim]── Log Deployment #{deployment_id} "
        f"({'last ' + str(tail) + ' lines' if tail > 0 else 'full'}) ──[/dim]"
    )
    for line in lines:
        console.print(line)
    console.print("[dim]── End of log ──[/dim]")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
