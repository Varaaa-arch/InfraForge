# InfraForge CLI

Command-line interface untuk berinteraksi dengan InfraForge API langsung dari terminal.

## Instalasi

### Dari source (development)

```bash
cd backend/
pip install -e .
# atau dengan uv:
uv sync
```

Setelah instalasi, command `infraforge-cli` tersedia di PATH.

### Verifikasi instalasi

```bash
infraforge-cli --help
```

---

## Konfigurasi

Konfigurasi disimpan di `~/.infraforge/config.json`. File ini berisi base URL dan token JWT yang digunakan untuk setiap request.

---

## Commands

### `config`

Tampilkan konfigurasi CLI yang aktif saat ini.

```bash
infraforge-cli config
```

Output menampilkan `base_url`, `username`, dan token yang sedang aktif (truncated).

---

### `login`

Login ke InfraForge API dan simpan token ke konfigurasi lokal.

```bash
infraforge-cli login \
  --url http://localhost:8000 \
  --username admin \
  --password secretpass
```

| Option | Short | Wajib | Keterangan |
|--------|-------|-------|-----------|
| `--url` | `-u` | ✅ | Base URL InfraForge API |
| `--username` | `-n` | ✅ | Username akun |
| `--password` | `-p` | ✅ | Password akun |

Setelah login berhasil, token disimpan otomatis dan digunakan untuk semua command berikutnya.

---

### `logout`

Hapus token autentikasi dari konfigurasi lokal.

```bash
infraforge-cli logout
```

---

### `deploy`

Picu proses deployment aplikasi ke server tertentu.

```bash
infraforge-cli deploy <APPLICATION_ID> --server-id <SERVER_ID>
```

```bash
# Contoh: deploy app ID 42 ke server ID 1
infraforge-cli deploy 42 --server-id 1

# Dengan branch override
infraforge-cli deploy 42 --server-id 1 --branch feature/new-ui
```

| Argumen / Option | Short | Wajib | Keterangan |
|------------------|-------|-------|-----------|
| `APPLICATION_ID` | — | ✅ | ID aplikasi yang akan di-deploy |
| `--server-id` | `-s` | ✅ | ID server target deployment |
| `--branch` | `-b` | ❌ | Override branch (default: branch dari konfigurasi aplikasi) |

Output berisi deployment ID, status, dan branch yang digunakan.

---

### `status`

Cek status deployment berdasarkan ID-nya.

```bash
infraforge-cli status <DEPLOYMENT_ID>
```

```bash
# Contoh
infraforge-cli status 10
```

Output berisi tabel dengan field: ID, Application ID, Server ID, Status, Branch, Commit SHA, Started At, Finished At, Duration.

Status yang mungkin:
- `pending` — menunggu dieksekusi
- `deploying` — sedang berjalan
- `success` — berhasil
- `failed` — gagal

---

### `logs`

Tampilkan log deployment dari file log yang tersimpan di server.

```bash
infraforge-cli logs <DEPLOYMENT_ID> [--tail N]
```

```bash
# Tampilkan 50 baris terakhir (default)
infraforge-cli logs 10

# Tampilkan 100 baris terakhir
infraforge-cli logs 10 --tail 100

# Tampilkan seluruh log
infraforge-cli logs 10 --tail 0
```

| Option | Short | Default | Keterangan |
|--------|-------|---------|-----------|
| `--tail` | `-n` | `50` | Jumlah baris terakhir (0 = semua) |

---

## Contoh Workflow Lengkap

```bash
# 1. Login
infraforge-cli login --url http://localhost:8000 --username alice --password pass123

# 2. Cek konfigurasi aktif
infraforge-cli config

# 3. Picu deployment
infraforge-cli deploy 5 --server-id 2 --branch main

# 4. Pantau status (gunakan ID dari output deploy)
infraforge-cli status 15

# 5. Lihat log deployment
infraforge-cli logs 15 --tail 100

# 6. Logout
infraforge-cli logout
```

---

## Kode Exit

| Kode | Arti |
|------|------|
| `0` | Sukses |
| `1` | Error (autentikasi, koneksi, resource tidak ditemukan, dsb.) |

---

## Live Logs via WebSocket

Untuk streaming log secara real-time (saat deployment masih berjalan), gunakan WebSocket endpoint langsung:

```
ws://localhost:8000/ws/deployments/<DEPLOYMENT_ID>/logs?token=<JWT_TOKEN>
```

Contoh dengan `websocat`:

```bash
TOKEN=$(cat ~/.infraforge/config.json | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
websocat "ws://localhost:8000/ws/deployments/15/logs?token=$TOKEN"
```

Koneksi akan otomatis tertutup dengan pesan `[INFRAFORGE:DONE]` saat deployment selesai.
