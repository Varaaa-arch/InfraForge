# Milestone 7 Fase 3 — Git Provider Integration & Live Deployment Logs

Fase ini melengkapi alur deployment berbasis Git dengan filter branch per
aplikasi, helper koneksi repository GitHub/GitLab, serta tampilan log build dan
compose yang benar-benar streaming di dashboard. Log tidak lagi menunggu proses
selesai: setiap baris yang ditulis subprocess langsung diteruskan ke browser
lewat WebSocket deployment yang sudah ada.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 7.3.1 | Backend: `applications.webhook_branches`, validasi schema, migrasi, matching webhook | `40d4abd` |
| 7.3.2 | Backend: subprocess `Popen` + reader thread, streaming baris ke file log, offset UTF-8 | `910b6b0` |
| 7.3.3 | Frontend: koneksi repository, filter branch per aplikasi, deep link webhook GitHub/GitLab | `937fec3` |
| 7.3.4 | Frontend: dialog log deployment real-time, perbaikan polling status WebSocket, E2E, dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Helper webhook | Manual + deep link ke halaman pengaturan webhook provider; tanpa PAT/OAuth dan tanpa tabel webhook baru |
| Secret webhook | Deployment token existing tetap menjadi secret HMAC GitHub atau `X-Gitlab-Token` GitLab |
| Filter branch | Disimpan per aplikasi sebagai list branch exact; tidak mendukung glob/pattern |
| Semantik kosong | `applications.webhook_branches = NULL` berarti fallback ke `applications.branch` |
| Branch default | `applications.branch` tetap dipakai deployment manual dan sebagai fallback filter |
| Provider | `github`, `gitlab`, dan `bitbucket`; webhook native hanya diproses untuk GitHub/GitLab |
| Log streaming | `subprocess.Popen` dengan reader thread untuk stdout/stderr, flush per baris |
| Transport UI | WebSocket deployment existing `WS /ws/deployments/{id}/logs` |
| Akses log | Endpoint dan tombol UI hanya untuk pemilik project |
| Selesai stream | Server mengirim sentinel `[INFRAFORGE:DONE]`; sentinel tidak ditampilkan sebagai log |

## Migrasi

`backend/alembic/versions/d4e6f8a1c2b3_add_application_webhook_branches.py`
(`down_revision = c8e4a1d9f2b3`):

- Tambah `applications.webhook_branches` bertipe `JSON`, nullable.
- `NULL` menjaga kompatibilitas aplikasi lama: filter memakai `branch`.

```bash
# DB host (dipakai pytest)
cd backend && uv run --no-dev alembic upgrade head

# DB Docker
docker compose exec -T backend uv run --no-dev alembic upgrade head
```

Tidak ada migrasi tambahan pada Paket 4. Rebuild image backend diperlukan jika
image lama belum memuat migrasi Fase 3.

## Backend

### File utama

| File | Peran |
|---|---|
| `app/models/application.py` | Kolom `webhook_branches` |
| `app/schemas/application.py` | Validasi create/update dan fallback response |
| `app/repositories/application_repository.py` | Default list branch saat create |
| `app/services/webhook_service.py` | `application_accepts_branch` untuk webhook legacy |
| `app/services/deployment_webhook_service.py` | Matching repository + branch webhook project |
| `app/services/deployment_service.py` | Streaming subprocess dan penulisan log per baris |
| `app/websocket/deployment_logs.py` | Tail log real-time, refresh status dari DB, sentinel selesai |
| `backend/tests/test_application_branches.py` | Validasi schema dan matching filter |
| `backend/tests/test_websocket.py` | Streaming, timeout, akses, refresh state |

### Kontrak branch webhook

`ApplicationResponse.webhook_branches` selalu berupa list:

- Data `NULL` dikembalikan sebagai `[application.branch]`.
- List tersimpan minimal 1 dan maksimal 20 branch.
- Setiap branch wajib non-empty, maksimal 100 karakter, tanpa spasi, dan unik.
- Pencocokan case-sensitive dan exact.
- `PATCH /applications/{id}` dengan `webhook_branches: null` mengembalikan
  aplikasi ke mode fallback `branch`.

Contoh payload:

```json
{
  "webhook_branches": ["main", "release", "hotfix"]
}
```

Webhook dengan `branch` di luar daftar diabaikan sebagai target deployment,
tetapi event tetap dibalas `202` agar provider tidak melakukan retry storm.

### Streaming log compose

`deployment_service._stream_subprocess` menjalankan build/up dengan `Popen`:

- stdout dan stderr dibaca dua reader thread.
- Setiap baris dikumpulkan untuk return value dan ditulis ke file log dengan
  lock agar output dua stream tidak saling merusak.
- Penulisan memakai `_append_log` dan flush per baris, sehingga WebSocket dapat
  membaca baris pertama sebelum proses selesai.
- Timeout default 600 detik; proses yang melewati batas dihentikan dan
  dilaporkan sebagai kegagalan.
- `_run_compose` tetap menulis marker `[InfraForge]`, dan exit code non-zero
  menghasilkan baris `[InfraForge] ERROR:`.

WebSocket deployment membaca file dari offset terakhir menggunakan `f.tell()`
(setelah `read`), bukan jumlah byte manual. Ini menjaga posisi tetap benar untuk
teks UTF-8 multi-byte.

### Perbaikan status polling

`_get_fresh_deployment` memanggil `db.expire_all()` sebelum membaca ulang
deployment. Proses deployment berjalan di session database lain; tanpa expire,
identity map SQLAlchemy dapat terus mengembalikan status `deploying` lama dan
sentinel `[INFRAFORGE:DONE]` tidak pernah dikirim.

Perilaku endpoint:

| Kondisi | Hasil |
|---|---|
| Token invalid/refresh token | Pesan error, close `4001` |
| Deployment bukan milik user | Pesan error, close `4003/4004` |
| `log_path` belum tersedia | Tunggu maksimal 30 detik |
| Deployment terminal tanpa file | Pesan error + sentinel + close |
| Deployment selesai | Semua baris dikirim, lalu sentinel + close |

## Frontend

### Detail project — Ringkasan

- Tombol **Hubungkan repository** / **Ubah repository** hanya tampil untuk
  pemilik project dengan permission deploy.
- Dialog berisi provider, URL repository HTTPS, dan branch default.
- Provider dideteksi otomatis dari hostname URL jika user belum memilih manual.
- URL repository di kartu informasi dapat diklik dan provider ditampilkan
  dengan label yang ramah.
- Tabel aplikasi menampilkan badge **Branch webhook** dan aksi **Atur branch**.
- Dialog filter branch mendukung tambah/hapus chip, validasi duplikat, spasi,
  panjang maksimal 100, dan batas 20 branch.
- Aplikasi lama tanpa `webhook_branches` tetap menampilkan branch deploy sebagai
  fallback.

### Detail project — CI/CD

- Panduan webhook native menampilkan payload URL dan aturan secret provider.
- Tombol deep link membuka:
  - GitHub: `<repo>/settings/hooks/new`
  - GitLab: `<repo>/-/hooks`
- URL `.git`, query string, fragment, dan trailing slash dinormalisasi sebelum
  membentuk tautan.
- Jika repository belum terhubung atau provider tidak didukung untuk webhook
  native, UI menampilkan arahan untuk menghubungkan repository lebih dulu.
- Dialog setelah token dibuat juga menyediakan deep link yang sama.

### Detail project — Deployment

- Setiap baris deployment memiliki tombol **Log** untuk pemilik project.
- Dialog log terhubung langsung ke WebSocket deployment dan menampilkan status
  `Menghubungkan`, `Live`, `Selesai`, atau `Error`.
- Baris baru muncul tanpa refresh; antrean render dibatch per animation frame
  dan daftar dibatasi 5000 baris di browser.
- Log otomatis scroll ke bawah, memiliki tombol salin (dengan fallback
  `execCommand`), dan tombol **Sambungkan ulang** saat koneksi gagal.
- Sentinel selesai dan pesan error protokol tidak dirender sebagai baris log.
- Log historis deployment terminal dapat dibuka ulang dan ditampilkan lengkap.

### File frontend utama

| File | Peran |
|---|---|
| `src/lib/git-provider.ts` | Deteksi provider dan pembentukan deep link webhook |
| `src/components/projects/repository-connection-dialog.tsx` | Form koneksi repository |
| `src/components/projects/application-branches-dialog.tsx` | Editor filter branch |
| `src/hooks/use-deployment-log-stream.ts` | Koneksi WebSocket, batching baris, retry |
| `src/components/projects/deployment-log-dialog.tsx` | Dialog log real-time |
| `src/components/projects/project-summary.tsx` | Tombol repo, tabel branch webhook |
| `src/components/projects/deploy-tokens-card.tsx` | Deep link webhook provider |
| `src/components/projects/deployment-history.tsx` | Tombol Log dan integrasi dialog |

## Verifikasi

### Backend

```bash
cd backend
uv run --no-dev pytest -q
uv run --no-dev ruff check app tests
uv run --no-dev mypy app
```

Hasil: **908 passed**, ruff bersih, mypy **120 source file** tanpa issue.
Tambahan Paket 4 adalah tes `test_refreshes_deployment_state_from_database`
untuk memastikan polling melakukan expire identity map.

### Frontend

```bash
cd frontend
npm run build
npm run lint
```

Hasil: build sukses. Lint tetap memiliki 3 warning baseline
(`use-log-stream.ts`, `button.tsx`, `badge.tsx`) yang tidak terkait fitur ini.

### E2E

Harness Chrome CDP tanpa puppeteer:

- `/tmp/opencode/ui-test/m7f3-package3-e2e.cjs` — **9/9 check lulus**
  untuk koneksi repository, filter branch, dan deep link GitHub.
- `/tmp/opencode/ui-test/m7f3-deployment-log-e2e.cjs` — **10/10 check lulus**
  untuk log live, sentinel, jumlah baris, reopen log historis, dan status API.

Cakupan E2E:

1. Project dan aplikasi uji dibuat lewat API; response branch fallback `[main]`.
2. Tabel menampilkan branch webhook default.
3. Dialog koneksi repository menyimpan URL/provider dan mengubah tombol menjadi
   **Ubah repository**.
4. Dialog filter menambah branch baru dan hasilnya tampil di tabel serta API.
5. Deep link GitHub mengarah ke `https://github.com/acme/demo-repo/settings/hooks/new`.
6. Deployment `deploying` dengan file log nyata dapat dibuka dari tombol Log.
7. Status dialog berubah menjadi `Live` dan baris awal tampil.
8. Baris yang ditambahkan ke file saat dialog terbuka muncul real-time.
9. Setelah status deployment menjadi `success`, UI menampilkan `Selesai`,
   sentinel tidak terlihat, dan jumlah baris sesuai.
10. Log historis dapat dibuka ulang, lalu status deployment diverifikasi lewat API.

Screenshot verifikasi:

- `/tmp/opencode/ui-test/m7f3-p3-repository-dialog.png`
- `/tmp/opencode/ui-test/m7f3-p3-branches-dialog.png`
- `/tmp/opencode/ui-test/m7f3-p3-ci-deeplink.png`
- `/tmp/opencode/ui-test/m7f3-p4-log-dialog.png`
- `/tmp/opencode/ui-test/m7f3-p4-log-reopen.png`

## Batasan

- Filter branch hanya mendukung pencocokan exact; tidak ada glob, regex, atau
  pola `release/*`.
- Bitbucket dapat disimpan sebagai provider project, tetapi webhook native dan
  deep link otomatis hanya tersedia untuk GitHub/GitLab.
- UI belum menyediakan create/edit aplikasi penuh; filter branch diatur dari
  tabel aplikasi yang sudah ada.
- Tombol dan endpoint log hanya untuk pemilik project, sesuai otorisasi backend.
- Log dialog menyimpan maksimal 5000 baris terakhir di browser; file log tetap
  lengkap di server.
- Helper webhook tidak membuat webhook otomatis di provider. Pengguna tetap
  membuka pengaturan provider dan menambahkan webhook secara manual.
- Analisis commit/tag dan rollback tetap mengikuti batasan Milestone 7 Fase 2.
