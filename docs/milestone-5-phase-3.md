# Milestone 5 Fase 3 — Tata Kelola Platform (RBAC, Audit Log & API Token)

Fase 3 menambahkan lapisan tata kelola di atas fitur operasional Fase 1–2:
peran pengguna (RBAC), riwayat audit persisten, personal access token untuk
CLI/CI-CD, dan halaman `/settings` lengkap. Section **Governance** di sidebar
kini berisi **Audit Logs** dan **Settings**.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 3.1 | RBAC: peran, matriks izin, enforcement endpoint, manajemen user admin | `e8a3ac3` |
| 3.2 | Audit log persisten via middleware + API & UI filter | `8631b88` |
| 3.3 | UI `/audit-logs`: filter, pagination, dialog detail | `fc16292` |
| 3.4 | Personal Access Token CLI/CI-CD (`if_<prefix>_<secret>`, scope, revoke) | `c8c3caf` |
| 3.5 | `/settings` bertab + UI menyesuaikan peran + menu pengguna | `808d58d` |
| 3.6 | Verifikasi menyeluruh + dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Sumber audit | Middleware otomatis dengan allowlist rute → action (bukan pemanggilan manual di handler) |
| Cakupan baca audit | Admin melihat semua; developer/viewer hanya aktivitas sendiri (dipaksa server-side) |
| Pengelolaan user | Hanya admin; tidak bisa mengubah akun sendiri; admin terakhir tidak bisa diturunkan/dinonaktifkan |
| Registrasi baru | Default `viewer`; user lama di-backfill `admin` (yang memang admin) dan lainnya `developer` |
| Token CLI/CI-CD | Personal Access Token: hash SHA-256, prefix untuk display, scopes, masa berlaku, `last_used_at`, revoke |
| Token plaintext | Hanya dikembalikan sekali saat dibuat; tidak pernah bisa dilihat lagi |
| Perubahan password | `POST /auth/change-password` (verifikasi password lama), audit `PASSWORD_CHANGE` |

## RBAC

### Peran & izin

| Permission | Admin | Developer | Viewer |
|---|:---:|:---:|:---:|
| Lihat project, server, container, deployment, alert | ✅ | ✅ | ✅ |
| Kelola project & repository | ✅ | ✅ | — |
| Kelola env var (termasuk reveal) | ✅ | ✅ | — |
| Deploy, rollback, health-check | ✅ | ✅ | — |
| Kelola aplikasi & image Docker | ✅ | ✅ | — |
| Lifecycle container (start/stop/restart) | ✅ | ✅ | — |
| Hapus container | ✅ | — | — |
| Kelola server & tes koneksi SSH | ✅ | — | — |
| Kelola channel notifikasi | ✅ | — | — |
| Kelola user | ✅ | — | — |

Implementasi: `app/core/roles.py` (`Role`, `Permission`, `ROLE_PERMISSIONS`,
`has_permission`), dependency `app/core/permissions.py`
(`require_permission`, `require_admin`). Semua endpoint mutasi memakai
dependency ini; `GET /users` dan `PATCH /users/{id}` hanya admin.

### API manajemen user

- `GET /users?limit=&offset=` → daftar user (admin).
- `PATCH /users/{user_id}` `{ "role": "admin|developer|viewer", "is_active": bool }`
  → ubah peran/status (admin). Menolak (400) perubahan akun sendiri dan
  penurunan/penonaktifan admin terakhir.

### Migration

`631d7c1523a9_add_role_to_users.py` menambah kolom `users.role`
(default `viewer`, index) dan mem-backfill user lama:
`admin → admin`, lainnya → `developer`. Seeder demo membuat `demo` sebagai
`developer`.

## Audit log

### Pipeline

`AuditLogMiddleware` mencocokkan `(method, path)` dengan allowlist
`AUDIT_RULES` (37 aturan). Untuk rute yang cocok:

1. Setelah response selesai, ambil user dari `request.state.current_user`
   (diisi `get_current_user`) atau hint `audit_username`/`audit_user_id`
   dari endpoint auth (login/register/logout).
2. Catat `action`, `method`, `path`, `status_code`, `resource_type`,
   `resource_id` (dari path param), IP (`x-forwarded-for` → fallback
   `request.client.host`), user agent, dan `details` terpilih.
3. Tulis ke `audit_logs` lewat session singkat (`SessionLocal`).

Catatan penting:

- **Body request tidak pernah dibaca/disimpan** — menghindari password dan
  secret masuk audit. Karena itu `resource_id` untuk aksi create yang id-nya
  ada di body bernilai `null` (mis. `PROJECT_CREATE`).
- **Request gagal tetap dicatat** (mis. `403` percobaan akses), sehingga
  percobaan yang ditolak ikut terlihat.
- Kegagalan menulis audit tidak menggagalkan request (di-log ke loguru).
- `AUDIT_PERSIST_ENABLED=false` mematikan penulisan (dipakai di test).
- `log_audit()` lama (loguru) tetap berjalan paralel untuk aksi bisnis.

### Skema `audit_logs`

`id, user_id (FK users ON DELETE SET NULL), username, action, method, path,
resource_type, resource_id, status_code, ip_address, user_agent, details JSON,
created_at` + index `(created_at)`, `(action)`, `(username)`.

### API

- `GET /audit-logs?username=&action=&from=&to=&limit=&offset=`
  → `{ items, total, limit, offset }`, `limit` ≤ 200.
  Non-admin: `username` dipaksa milik sendiri; filter username lain → 403.
- `GET /audit-logs/filters`
  → `{ actions, usernames, is_admin }`; non-admin hanya menerima username
  sendiri.

### UI `/audit-logs`

Filter user (admin), aksi, rentang waktu (`from`/`to`), badge scope
(**Semua aktivitas** vs **Aktivitas saya**), tabel dengan status HTTP,
pagination, dialog detail (request, resource, IP/UA, details), auto-refresh
30 detik.

## Personal Access Token

Format: `if_<prefix8hex>_<secret64hex>`. Database menyimpan
`sha256(token)` (unik), prefix untuk display (`if_ab12cd34…`), `scopes`,
`expires_at`, `last_used_at`, `revoked_at`.

### Autentikasi

`get_current_user` mencoba JWT access token lebih dulu; bila bukan JWT valid,
token dicari berdasarkan hash di `api_tokens` (harus belum revoked dan belum
kedaluwarsa). `last_used_at` diperbarui maksimal sekali per menit. User harus
aktif. Token dengan scope `["read"]` hanya boleh memakai method
`GET/HEAD/OPTIONS`; mutasi ditolak 403.

### API

| Method | Path | Keterangan |
|---|---|---|
| `POST` | `/api-tokens` | Buat token; response memuat `token` plaintext **sekali** |
| `GET` | `/api-tokens` | Metadata token milik sendiri (tanpa hash/plaintext) |
| `DELETE` | `/api-tokens/{id}` | Revoke token milik sendiri (idempoten) |

Contoh:

```bash
curl -X POST http://127.0.0.1:8000/api-tokens \
  -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" \
  -d '{"name":"github-actions","scopes":["read"],"expires_in_days":90}'

curl http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer if_ab12cd34_<secret>"
```

Audit middleware mencatat `API_TOKEN_CREATE` dan `API_TOKEN_REVOKE`.

## Halaman `/settings`

Tab: **Profil**, **Keamanan**, **API Token**, **Pengguna** (admin saja),
**Notifikasi** (tautan ke manajemen channel di `/alerts`). Tab aktif disimpan
di query `?tab=`. `?tab=users` untuk non-admin dialihkan ke Profil.

User menu menampilkan badge peran dan shortcut ke Pengaturan/API token.
Sidebar **Governance** berisi Audit Logs dan Settings.

## Verifikasi

### Backend

```
pytest               → 774 passed, 0 failed
ruff check           → 10 temuan (baseline, tidak bertambah)
mypy app             → 3 temuan (baseline, app/worker.py)
alembic heads        → 2abe02d9fbdc (satu head)
alembic current      → 2abe02d9fbdc (host & Docker)
```

Pertumbuhan test: `683 → 696` (RBAC, +13) `→ 750` (audit middleware, +54)
`→ 761` (API audit, +11) `→ 774` (API token + aturan audit, +13).

Migrasi `2abe02d9fbdc` diuji naik–turun di host
(`downgrade -1 → upgrade head`) dan diterapkan di Docker.

### Frontend

```
npm run build → sukses
npm run lint  → 3 warning (baseline: fast-refresh & efek React)
```

### E2E Playwright (Chrome headless)

| Skrip | Cakupan | Hasil |
|---|---|---|
| `audit-e2e.cjs` | Admin: semua aktivitas, filter aksi/user/tanggal, reset, dialog detail. Developer: scope sendiri, tanpa filter user | **17/17** |
| `api-tokens-e2e.cjs` | Buat token read-only & penuh, dialog token sekali, validasi PAT via API, penolakan write, revoke & status | **19/19** |
| `settings-e2e.cjs` | Tab settings, edit profil + user menu, validasi password, ubah peran pengguna, gating viewer di servers/env/container/channel | **33/33** |
| `regression-e2e.cjs` | Semua halaman utama, sidebar, alur project/env var, reveal, audit `ENV_VAR_REVEAL`, tanpa page error | **26/26** |

### Smoke API (live Docker)

| Aktor | Request | Status |
|---|---|---|
| admin | `GET /users`, `GET /servers`, `GET /audit-logs` | `200` |
| demo (developer) | `GET /users` | `403` |
| demo | `POST /servers` | `403` (tercatat di audit) |
| demo | `GET /servers`, `GET /audit-logs`, `GET /projects/6/env` | `200` |
| demo | `GET /audit-logs` (22 baris) | semua milik `demo` |
| PAT read-only | `GET /projects` → `200`; `POST /projects` → `403` "akses baca" | sesuai |
| PAT setelah revoke | `GET /auth/me` | `401` |

## Catatan operasional

- **Token hanya tampil sekali**. Simpan di secret manager CI/CD; bila hilang,
  revoke lalu buat baru.
- **Revoke token tidak mencabut sesi JWT** yang sedang aktif. JWT tetap valid
  sampai kedaluwarsa.
- **Scope token tidak menaikkan izin**: permission peran tetap berlaku
  (viewer dengan token `write` tetap tidak bisa deploy).
- **Audit mencatat percobaan gagal** (403/422) selama rute cocok allowlist.
- **Retensi audit belum ada** — tabel tumbuh monoton. Untuk produksi jangka
  panjang, jadwalkan pembersihan/arsip.
- **Password admin demo** pada database contoh: `admin` / `admin1234`
  (dokumentasi lokal, bukan default produksi).

## Di luar scope Fase 3

2FA, verifikasi email, SSO/OIDC, scope token per project, rotasi token
terjadwal, export/retensi audit otomatis, dan notifikasi perubahan peran.
