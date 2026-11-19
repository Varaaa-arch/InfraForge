# Milestone 7 Fase 2 — Deployment Version History & Instant Rollback

Fase ini melengkapi riwayat deployment M6 dengan metadata versi yang dapat
diaudit dan operasi rollback yang aman. Setiap deployment kini menyimpan tag dan
identitas pemicu, sementara rollback dibuat sebagai deployment baru yang
menyalin snapshot `tag`, `commit_sha`, branch, dan compose path dari versi stabil
yang dipilih.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 7.2.1 | Backend: kolom `tag`/`triggered_by`, migrasi, metadata trigger manual/CI/webhook | `3549359` |
| 7.2.2 | Backend: rollback asynchronous, snapshot versi, checkout commit exact | `71dcdac` |
| 7.2.3 | Frontend: tabel versi, identitas pemicu, dialog dan tombol rollback | `dbb8f54` |
| 7.2.4 | Verifikasi E2E + dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Semantik tag | `tag` adalah tag Git yang menunjuk tepat ke commit deployment; dideteksi setelah clone berhasil |
| Sumber versi | `commit_sha` adalah sumber utama rollback; `tag` disimpan sebagai metadata dan fallback |
| Rollback | Membuat deployment baru (`is_rollback=true`, `rollback_of=<target>`), bukan menimpa record lama |
| Respons API | `POST /deployments/{id}/rollback` membalas `202 Accepted`; eksekusi berjalan di background |
| Snapshot | Rollback menyalin `tag`, `commit_sha`, `branch`, dan `compose_path_snapshot` target |
| Compose path | Deployment memakai snapshot compose path bila ada, lalu fallback ke konfigurasi aplikasi |
| Identitas pemicu | Manual = username; CI = `deploy-token:<nama token>`; webhook memakai identitas pemicu yang tersedia |
| Pemilihan target | User memilih deployment sukses lama; UI tidak menampilkan rollback untuk rilis stabil terbaru |
| Concurrency | Rollback memakai lock deployment yang sama dan mengembalikan `409` bila aplikasi sedang deploy |
| Kompatibilitas | Deployment lama tanpa tag/commit tetap dapat di-rollback memakai branch dan compose path saat ini |

## Migrasi

`backend/alembic/versions/c8e4a1d9f2b3_add_deployment_version_metadata.py`
(`down_revision = a7d2e5f8c1b4`):

- Tambah `deployments.tag` (`varchar(100)`, nullable).
- Tambah `deployments.triggered_by` (`varchar(160)`, nullable).

```bash
# DB host (dipakai pytest)
cd backend && uv run --no-dev alembic upgrade head

# DB Docker
docker compose up -d --build backend
docker compose exec -T backend uv run --no-dev alembic upgrade head
```

File migrasi harus ikut masuk image backend. Rebuild container diperlukan jika
image lama belum memuat migrasi ini.

## Backend

### File utama

| File | Peran |
|---|---|
| `app/models/deployment.py` | Kolom `tag` dan `triggered_by` |
| `app/schemas/deployment.py` | Field versi pada response dan payload trigger |
| `app/repositories/deployment_repository.py` | Menyimpan tag, commit, identitas pemicu, snapshot compose |
| `app/services/deployment_service.py` | `create_rollback_deployment`, snapshot versi, eksekusi clone/compose |
| `app/services/git_service.py` | Clone tag/commit exact, verifikasi SHA, deteksi tag pada HEAD |
| `app/api/deployments.py` | Endpoint rollback `202` dan penjadwalan background |
| `app/services/deployment_queue.py` | Lock aplikasi dan eksekusi background bersama deployment biasa |

### Metadata versi

`DeploymentResponse` sekarang mengekspos:

```json
{
  "id": 42,
  "branch": "main",
  "commit_sha": "f4c1a2...",
  "tag": "v1.4.2",
  "triggered_by": "deploy-token:pipeline-production",
  "is_rollback": true,
  "rollback_of": 37,
  "compose_path_snapshot": "deploy/compose-v1.yml",
  "started_at": "2026-11-19T10:00:00Z",
  "finished_at": "2026-11-19T10:01:12Z",
  "duration": 72.0
}
```

Deployment branch biasa menyimpan tag yang ditemukan tepat di HEAD setelah
clone. Kondisi ini penting karena tag di repository dapat berpindah; riwayat
tetap menyimpan commit yang benar-benar dieksekusi.

### Endpoint rollback

`POST /deployments/{deployment_id}/rollback`

| Status | Kondisi |
|---|---|
| `202` | Deployment rollback dibuat dan dijadwalkan di background |
| `403` | User tidak memiliki permission `deploy` |
| `404` | Deployment target tidak ditemukan atau bukan milik user |
| `409` | Aplikasi sedang dalam proses deployment |
| `422` | Target bukan deployment sukses atau server target sudah tidak ada |

Alur:

1. Validasi target milik aplikasi yang dapat diakses user.
2. Pastikan target berstatus `success`.
3. Tentukan compose path dari snapshot target atau konfigurasi aplikasi.
4. Cek Redis lock dan status aplikasi di database.
5. Pastikan server target masih ada.
6. Buat record deployment baru berstatus `pending`.
7. Jadwalkan `run_deployment_background` dan catat audit `ROLLBACK`.
8. UI menerima response instan dan memantau status lewat polling/WebSocket.

Rollback tidak menghentikan versi aktif terlebih dahulu. Versi lama baru
digantikan setelah clone, build, `docker compose up`, dan health check rollback
berhasil.

### Checkout versi exact

`git_service.clone_repository` menerima `tag` dan `commit_sha`:

- `commit_sha` terisi: clone penuh tanpa shallow filter, checkout SHA, lalu
  verifikasi bahwa HEAD cocok dengan SHA tersebut.
- Hanya `tag` terisi: shallow clone pada tag tersebut.
- Tanpa keduanya: perilaku branch sebelumnya tetap dipakai.

Jika checkout exact gagal, deployment ditandai `failed`; rollback tidak diam-diam
memakai branch lain.

### Contoh curl

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/deployments/42/rollback"
```

Response `202` berisi record deployment baru dengan `status: "pending"`.

## Frontend

Tab **Deployment** pada detail project sekarang menampilkan:

- Kolom **Tag** dan **Commit** (hash pendek, full SHA ada di tooltip).
- Branch dan **Waktu rilis** (`finished_at`, atau `started_at` selama berjalan).
- **Pemicu**: label sumber (`Manual`, `Webhook`, `CI Token`), badge `Rollback`,
  dan identitas `triggered_by`.
- Status, durasi, serta aksi rollback.
- Tombol **Rollback** hanya muncul untuk deployment sukses lama yang bukan
  rilis stabil terbaru pada aplikasi tersebut.
- Tombol disembunyikan untuk viewer dan dinonaktifkan saat aplikasi sedang
  deployment.
- Dialog konfirmasi menyebut aplikasi, tag, commit, dan branch target.
- Setelah `202`, feedback sukses tampil dan daftar deployment langsung
  di-invalidate; baris rollback baru muncul dengan badge `Rollback`.
- Polling 5 detik aktif selama ada deployment `pending`/`deploying`, lalu
  melambat menjadi 30 detik.

## Verifikasi

### Backend

```bash
cd backend
uv run --no-dev pytest -q
uv run --no-dev ruff check app tests
uv run --no-dev mypy app
```

Hasil: **888 passed**, ruff bersih, mypy **120 source file** tanpa issue.

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

Hasil: build sukses. Lint tetap memiliki 3 warning baseline yang tidak terkait
fitur ini.

### E2E

Harness di `/tmp/opencode/ui-test/m7-version-rollback-e2e.cjs` memakai Chrome
CDP tanpa puppeteer. Hasil: **37/37 check lulus**.

Cakupan E2E:

1. Tabel menampilkan tag, commit pendek, branch, waktu rilis, status, dan durasi.
2. Identitas `deploy-token:e2e-pipeline` tampil sebagai pemicu CI.
3. Deployment gagal tanpa tag memakai fallback `—`.
4. Tombol rollback hanya muncul pada versi sukses lama, bukan rilis terbaru
   atau deployment gagal.
5. Dialog konfirmasi memuat tag dan commit target; tombol batal tidak mengirim
   request.
6. Konfirmasi rollback mengirim satu request, endpoint membalas `202`, feedback
   tampil, dan baris rollback baru muncul dengan badge `Rollback`.
7. API dan database menyimpan `rollback_of`, `tag`, `commit_sha` lengkap,
   `compose_path_snapshot`, serta `triggered_by`.
8. Audit `ROLLBACK` tercatat dengan target deployment yang benar.
9. Viewer menerima `403` dari endpoint rollback dan tidak melihat tombol
   rollback di UI.

E2E memakai deployment sukses hasil seed dan repository sengaja tidak valid agar
proses background selesai cepat. Yang diverifikasi end-to-end adalah alur UI,
kontrak `202`, snapshot versi, record database, audit, dan RBAC. Eksekusi clone
commit exact serta jalur sukses compose/health check diverifikasi oleh unit test
backend.

## Batasan

- Rollback membuat deployment baru; container dari deployment lama tidak
  dihapus otomatis.
- Deployment legacy tanpa `commit_sha`/`tag` hanya dapat kembali ke branch, bukan
  ke commit exact.
- Compose path fallback ke konfigurasi aplikasi bila deployment lama belum
  memiliki snapshot.
- Rollback ke rilis stabil terbaru tidak ditampilkan karena tidak mengubah versi.
- Tag Git dapat berpindah; `commit_sha` tetap menjadi acuan exact.
- Keberhasilan rollback tetap bergantung pada repository, Docker daemon, dan
  health check aplikasi.
