# Milestone 6 Fase 3 — CI/CD Trigger Tokens & GitHub Integration

Fase ini menutup celah terakhir alur deployment: pipeline CI/CD dapat memicu
deployment project tanpa menyimpan JWT user. Setiap project memiliki deployment
token sendiri, endpoint publik menerima trigger dan menjalankan deployment di
background, lalu statusnya muncul instan di riwayat deployment project.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 6.5 | Backend: model `deployment_tokens`, kolom `trigger_source`, API manajemen, endpoint publik trigger, audit | `Feat: deployment token CI/CD dan endpoint publik trigger` |
| 6.6 | Frontend: tab CI/CD (buat/cabut token + snippet) dan tab riwayat deployment dengan polling | `Feat: UI deployment token CI/CD dan riwayat deployment project` |
| 6.7 | Verifikasi E2E + dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Cakupan token | Satu token terikat ke satu project; tidak bisa lintas project |
| Format token | `dt_<8hex>_<64hex>`; prefix disimpan untuk UI, hanya hash SHA-256 yang masuk DB |
| Plaintext | Hanya dikembalikan sekali saat pembuatan (pola Personal Access Token) |
| Endpoint publik | `POST /deploy/trigger/{token}` tanpa JWT; autentikasi = token pada path |
| Path eksternal | Lewat nginx frontend menjadi `/api/deploy/trigger/{token}` (prefix `/api/` di-strip) |
| Eksekusi | Background task (pola webhook GitHub): record `pending` → 202 → `run_deployment_background` |
| Multi-aplikasi | 1 aplikasi → otomatis; >1 aplikasi → wajib `application_id` di body |
| Server target | `server_id` opsional di body (harus milik owner); default server pertama owner |
| Branch | `branch` opsional di body; default branch aplikasi |
| Concurrency | Cek Redis lock per aplikasi → 409 berisi `deployment_id` yang sedang jalan |
| Riwayat | Kolom baru `deployments.trigger_source` (`manual`/`github_webhook`/`ci_token`) |
| Audit | `DEPLOY_TOKEN_CREATE`, `DEPLOY_TOKEN_REVOKE`, `DEPLOY_TRIGGER`; token mentah tidak masuk detail/path audit |

## Migrasi

`backend/alembic/versions/f3a9c1d2e4b7_add_deployment_tokens.py`
(`down_revision = b7c2d4e9f1a3`):

- Tabel `deployment_tokens`: `project_id` (CASCADE), `created_by` (SET NULL),
  `name`, `token_hash` (unique index), `prefix`, `last_used_at`, `expires_at`,
  `revoked_at`, `created_at`.
- Kolom `deployments.trigger_source` (varchar 20, default `manual`,
  NOT NULL) — baris lama otomatis bernilai `manual`.

```bash
# DB host (dipakai pytest)
cd backend && uv run --no-dev alembic upgrade head

# DB Docker
docker compose exec -T backend uv run --no-dev alembic upgrade head
```

## Backend

### Model & repository

- `app/models/deployment_token.py` — `DeploymentToken`; helper `is_revoked`
  dan `is_expired`.
- `app/models/deployment.py` — enum `TriggerSource` dan kolom
  `trigger_source`.
- `app/repositories/deployment_token_repository.py` — lookup per project,
  lookup hash, list, create, revoke, update `last_used_at`.

### Service

`app/services/deployment_token_service.py`:

- `create_token` menghasilkan plaintext `dt_<prefix>_<secret>` dan menyimpan
  hash SHA-256 + prefix.
- `find_active_by_token` menolak token yang dicabut atau kedaluwarsa.
- `touch_last_used` menulis `last_used_at` maksimal sekali per menit.
- `resolve_target` memilih aplikasi (auto jika tunggal, validasi
  `application_id` bila banyak) dan server (validasi kepemilikan bila
  dikirim, fallback server pertama owner).
- `trigger_deployment` membuat deployment record dengan
  `trigger_source=ci_token` memakai `deployment_service.create_deployment_record`.

### API

Manajemen (JWT, hanya owner project; mutasi butuh izin `deploy`):

| Method | Path | Keterangan |
|---|---|---|
| `POST` | `/projects/{project_id}/deploy-tokens` | Buat token; plaintext hanya di response ini |
| `GET` | `/projects/{project_id}/deploy-tokens` | List metadata (prefix/status/last used) |
| `DELETE` | `/projects/{project_id}/deploy-tokens/{token_id}` | Cabut token (idempotent) |

Publik (tanpa JWT):

| Method | Path | Status | Keterangan |
|---|---|---|---|
| `POST` | `/deploy/trigger/{token}` | `202` | `{deployment_id, application_id, application_name, branch, status, message}` |
| | | `404` | Token tidak valid/dicabut/kedaluwarsa |
| | | `409` | Aplikasi sedang deploying (`deployment_id` disebut di pesan) |
| | | `422` | Project tanpa aplikasi, `application_id` asing, atau server tidak valid |

Body opsional: `{"application_id": 12, "branch": "main", "server_id": 3}`.

Urutan proses endpoint:

1. Resolusi token aktif (hash lookup).
2. Resolusi aplikasi & server target (422 bila ambigu/tidak valid).
3. Cek Redis lock aplikasi → 409 bila ada deployment berjalan.
4. Buat deployment record `pending` + `trigger_source=ci_token`.
5. Perbarui `last_used_at`.
6. Daftarkan `run_deployment_background` lewat `BackgroundTasks`.
7. Balas 202; status berikutnya terlihat di riwayat deployment.

### Riwayat per project

`GET /deployments` menerima query baru `project_id` (hanya project milik user,
404 bila bukan owner) untuk menampilkan seluruh deployment aplikasi dalam satu
project. Setiap item response menyertakan `trigger_source`.

### Audit

| Action | Kapan | Atribusi |
|---|---|---|
| `DEPLOY_TOKEN_CREATE` | `POST` token lewat middleware | user login |
| `DEPLOY_TOKEN_REVOKE` | `DELETE` token lewat middleware | user login |
| `DEPLOY_TRIGGER` | Setiap request trigger (termasuk 404/409/422) | Sukses: `username = deploy-token:<nama>`, `resource_id = id token`; gagal: tanpa identitas token |

Middleware audit diperluas agar endpoint publik dapat mengisi
`request.state.audit_username`, `audit_resource_id`, `audit_details`, dan
`audit_path`. Handler trigger mengisi `audit_path = /deploy/trigger/[redacted]`
sehingga **token mentah tidak tersimpan** di kolom path maupun details. Token
tetap ada di URL request asli, jadi tetap gunakan HTTPS dan secret manager.

## Frontend

- **Tab CI/CD** di detail project:
  - Form nama + masa berlaku (30/90/365 hari/tanpa kedaluwarsa).
  - Dialog plaintext sekali dengan tombol salin dan contoh curl berisi token.
  - Tabel token: prefix, status (Aktif/Dicabut/Kedaluwarsa), kedaluwarsa,
    terakhir dipakai, aksi cabut.
  - Snippet siap pakai: curl dan GitHub Actions (`INFRAFORGE_TRIGGER_URL`).
  - Panel pengelolaan hanya untuk pemilik project dengan peran developer/admin;
    pengguna lain melihat notice read-only.
- **Tab Deployment** di detail project:
  - Tabel 50 deployment terakhir: aplikasi, branch, commit, pemicu
    (Manual/GitHub Webhook/CI Token + badge Rollback), status, durasi, waktu.
  - Polling adaptif: 5 detik selama ada status `pending`/`deploying`, 30 detik
    saat idle — status CI/CD muncul tanpa refresh manual.

## Contoh pemakaian

```bash
curl -fsS -X POST "https://infraforge.example.com/api/deploy/trigger/<token>" \
  -H "Content-Type: application/json" \
  -d '{"branch":"main"}'
```

```yaml
# .github/workflows/deploy.yml
- name: Deploy via InfraForge
  run: |
    curl -fsS -X POST "${{ secrets.INFRAFORGE_TRIGGER_URL }}" \
      -H "Content-Type: application/json" \
      -d '{"branch":"${{ github.ref_name }}"}'
```

Isi secret `INFRAFORGE_TRIGGER_URL` dengan URL lengkap
`https://<host>/api/deploy/trigger/<token>`. Untuk project multi-aplikasi
tambahkan `"application_id": <id>`.

## Pengujian

| Pemeriksaan | Hasil |
|---|---|
| `uv run --no-dev pytest -q` | **842 passed** (28 warning) |
| `uv run --no-dev ruff check app tests` | **0 temuan** |
| `uv run --no-dev mypy app` | **0 error** (118 source file) |
| Frontend `npm run lint` | 3 warning baseline, tanpa warning baru |
| Frontend `npm run build` | Sukses (`tsc -b && vite build`) |
| Alembic host & Docker | `f3a9c1d2e4b7 (head)` |
| E2E CI/CD token | **26/26** |

Test backend baru `tests/test_deploy_tokens.py` (16 test) mencakup:

- Plaintext sekali pakai, hash tersimpan, prefix, list tanpa secret.
- Kepemilikan project, RBAC developer/viewer.
- Trigger sukses (202, record `pending`, `trigger_source=ci_token`, background
  dipanggil, `last_used_at` terisi), override branch, multi-aplikasi,
  aplikasi/server asing, project tanpa aplikasi/server.
- Token tidak dikenal/dicabut/kedaluwarsa → 404; lock aktif → 409 tanpa record.
- Filter `GET /deployments?project_id=` dan default `trigger_source` manual.
- Aturan audit dan atribusi `DEPLOY_TRIGGER` (token mentah tidak masuk audit).

Skenario E2E `/tmp/opencode/ui-test/cicd-token-e2e.cjs` (Chrome headless via
CDP) membuktikan:

1. Admin membuat deployment token lewat tab CI/CD; plaintext berformat
   `dt_<8hex>_<64hex>` dan hanya tampil di dialog.
2. Prefix dan nama token muncul di tabel; token asing → 404.
3. `POST /deploy/trigger/<token>` → 202 dengan deployment `pending`.
4. Riwayat project langsung menampilkan baris baru dengan pemicu **CI Token**,
   branch `main`, dan status yang berubah real-time sampai **Failed**
   (repository uji sengaja tidak valid).
5. API riwayat mencatat `trigger_source=ci_token` dan status `failed`.
6. Cabut token lewat UI → status **Dicabut**; trigger berikutnya → 404.
7. Cleanup menghapus project (cascade token/aplikasi/deployment) dan server uji.

## Keterbatasan

- Token berada di path URL, sehingga dapat terlihat di access log proxy/server.
  Gunakan HTTPS dan secret manager; audit InfraForge sendiri meredaksi path.
- Belum ada rate limiting khusus endpoint trigger. Perlindungan saat ini:
  hash lookup, status token, dan Redis lock per aplikasi.
- Satu token hanya untuk satu project; belum ada token level organisasi.
- Trigger tidak memvalidasi apakah commit/branch berasal dari repository yang
  sama — server tetap menjalankan clone sesuai konfigurasi aplikasi.
- `server_id` pada deployment masih metadata (eksekusi compose berjalan di
  host backend); belum ada deployment ke server remote via SSH.
- Riwayat menampilkan 50 deployment terakhir per project; belum ada halaman
  global lintas project atau tombol rollback di UI.
