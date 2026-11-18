# Milestone 7 Fase 1 — Webhook Receiver & Deployment Automation

Fase ini memperluas deployment token M6 Fase 3 menjadi receiver webhook yang
siap dipakai pipeline CI/CD nyata. Token bisa dibatasi ke satu aplikasi, event
GitHub/GitLab diverifikasi dengan signature/secret, deployment tetap berjalan
di background, dan hasilnya dikirim ke channel alert yang sudah ada.

Endpoint lama `POST /deploy/trigger/{token}` tetap didukung agar integrasi M6
tidak rusak. Semua fitur baru bersifat aditif.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 7.1 | Backend: scope token aplikasi, webhook receiver CI/GitHub/GitLab, audit, migrasi | `441a193` |
| 7.2 | Notifikasi queued/success/failed ke channel alert | `bc6f49e` |
| 7.3 | Frontend: select cakupan aplikasi, tabel scope, snippet dan panduan webhook | `af85e37` |
| 7.4 | Verifikasi E2E + dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Kompatibilitas | Enhance token M6; endpoint dan response lama tetap berlaku |
| Cakupan token | `application_id` nullable: `NULL` = project-wide, terisi = hanya aplikasi tersebut |
| Endpoint baru | `POST /v1/deploy/webhook/{token}`; eksternal `/api/v1/deploy/webhook/{token}` |
| GitHub native | `X-GitHub-Event` + `X-Hub-Signature-256`; HMAC-SHA256 raw body dengan token path sebagai secret |
| GitLab native | `X-Gitlab-Event` + `X-Gitlab-Token`; constant-time compare dengan token path |
| CI sederhana | Tanpa header event; body JSON opsional `application_id`, `branch`, `server_id` |
| Trigger source | Token webhook tetap mencatat `deployments.trigger_source = ci_token` |
| Target native | Project-wide: semua aplikasi yang repository + branch-nya cocok; token aplikasi: hanya aplikasi terikat |
| Idempotency | `X-GitHub-Delivery` → `github:*`, `X-Gitlab-Event-UUID` → `gitlab:*`, `Idempotency-Key` → `ci:*` |
| Duplikat | Balas `202` dengan `accepted=false`; tidak membuat deployment baru |
| Concurrency | Mode CI sederhana: `409` bila aplikasi sedang deploy. Native: aplikasi yang terkunci di-skip |
| Notifikasi | Hanya CI/webhook; queued/success severity `info`, failed `critical`; best-effort |
| Batas commit | Commit SHA event hanya diaudit; deployment tetap clone HEAD branch |

## Migrasi

`backend/alembic/versions/a7d2e5f8c1b4_add_deployment_token_application_scope.py`
(`down_revision = f3a9c1d2e4b7`):

- Tambah `deployment_tokens.application_id` (nullable, FK `applications.id`,
  `ON DELETE CASCADE`, index).
- Token lama otomatis menjadi project-wide (`NULL`).

```bash
# DB host (dipakai pytest)
cd backend && uv run --no-dev alembic upgrade head

# DB Docker
docker compose exec -T backend uv run --no-dev alembic upgrade head
```

## Backend

### File utama

| File | Peran |
|---|---|
| `app/services/deployment_webhook_service.py` | Deteksi sumber, parsing/verifikasi, resolusi aplikasi, pembuatan deployment |
| `app/api/deploy_tokens.py` | Endpoint manajemen, endpoint lama, handler webhook baru, audit |
| `app/services/deployment_token_service.py` | Validasi scope aplikasi dan resolusi target |
| `app/services/deployment_notification_service.py` | Payload dan pengiriman notifikasi deployment |
| `app/services/deployment_queue.py` | Hook notifikasi terminal setelah background deployment |
| `app/middleware/audit_middleware.py` | Rule audit `DEPLOY_WEBHOOK` + redaksi path |

### Kontrak endpoint

| Method | Path | Status | Keterangan |
|---|---|---|---|
| `POST` | `/v1/deploy/webhook/{token}` | `202` | Diterima/di-skip; cek `accepted` |
| | | `400` | Body bukan JSON object / schema CI tidak valid |
| | | `401` | Signature GitHub / secret GitLab salah |
| | | `404` | Token tidak valid, dicabut, atau kedaluwarsa |
| | | `409` | Mode CI sederhana: aplikasi sedang deployment |
| | | `422` | Target CI ambigu/tidak ditemukan |
| `POST` | `/deploy/trigger/{token}` | `202` | Endpoint legacy M6, tetap berfungsi |

`accepted=false` tetap memakai HTTP `202` untuk event yang valid tetapi tidak
menghasilkan deployment: event non-push, tidak ada aplikasi cocok, duplikat,
atau semua target sedang terkunci. Ini mencegah GitHub/GitLab melakukan retry
berulang pada event yang memang tidak relevan.

Contoh response sukses:

```json
{
  "success": true,
  "data": {
    "accepted": true,
    "message": "2 deployment dijadwalkan",
    "source": "github",
    "event": "push",
    "branch": "main",
    "deployment_ids": [41, 42],
    "deployments": [
      {
        "deployment_id": 41,
        "application_id": 12,
        "application_name": "api",
        "branch": "main",
        "status": "pending"
      },
      {
        "deployment_id": 42,
        "application_id": 13,
        "application_name": "worker",
        "branch": "main",
        "status": "pending"
      }
    ],
    "skipped_application_ids": []
  }
}
```

### GitHub native

Konfigurasi repository → Settings → Webhooks:

- Payload URL: `https://<host>/api/v1/deploy/webhook/<token>`
- Content type: `application/json`
- Secret: deployment token
- Event: **Just the push event**

Backend memverifikasi `X-Hub-Signature-256: sha256=<hmac>` terhadap raw body.
Repository dibaca dari `repository.html_url` / `clone_url`; branch dari `ref`;
commit dari `head_commit.id`; delivery dari `X-GitHub-Delivery`.

### GitLab native

Konfigurasi project → Settings → Webhooks:

- URL: `https://<host>/api/v1/deploy/webhook/<token>`
- Secret token: deployment token
- Trigger: **Push events**

Backend membandingkan `X-Gitlab-Token` secara constant-time. Repository dibaca
dari `repository.git_http_url` / `project.git_http_url`; branch dari `ref`;
commit dari `checkout_sha` atau `after`; delivery dari `X-Gitlab-Event-UUID`
(atau `Idempotency-Key`). Event `Push Hook` dinormalisasi menjadi `push`.

### CI sederhana

Tanpa header native, endpoint memakai mode CI. Contoh:

```bash
curl -fsS -X POST "https://infraforge.example.com/api/v1/deploy/webhook/<token>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: build-2026-11-18-001" \
  -d '{"branch":"main"}'
```

- Token aplikasi tidak memerlukan `application_id`.
- Token project-wide dengan >1 aplikasi wajib mengirim `application_id`.
- `server_id` opsional; harus milik owner project.
- `branch` opsional; default branch aplikasi.

### Audit

Middleware menambahkan rule `POST /v1/deploy/webhook/[^/]+` dengan action
`DEPLOY_WEBHOOK`. Handler langsung mengisi `audit_path` menjadi
`/v1/deploy/webhook/[redacted]`, sehingga token mentah tidak masuk kolom path.

Detail audit yang dicatat:

- `source` (`ci`/`github`/`gitlab`), `event`, `branch`
- `repository`, `commit_sha`, `delivery_id`
- `application_ids`, `deployment_ids`, `skipped_application_ids`
- `outcome` (`scheduled`, `partial`, `duplicate`, `no_match`, `ignored_event`,
  `invalid_signature`, `invalid_payload`, `invalid_target`, `conflict`,
  `locked`, `invalid_token`)

Atribusi sukses memakai `username = deploy-token:<nama token>` dan
`resource_id = <id token>`. Request dengan token tidak valid tidak memiliki
identitas token. Body webhook tidak disimpan.

### Notifikasi

`deployment_notification_service` mengirim notifikasi ke channel alert aktif
yang threshold severity-nya terpenuhi:

| Event | Severity | Kapan |
|---|---|---|
| `queued` | `info` | Deployment CI/webhook berhasil dijadwalkan |
| `success` | `info` | Deployment selesai sukses |
| `failed` | `critical` | Deployment gagal |

- Hanya `trigger_source` `ci_token` atau `github_webhook`.
- Deployment manual dan rollback tidak dikirim.
- Format mengikuti tipe channel: Discord embed, Slack blocks, Telegram HTML.
- Pengiriman best-effort: kegagalan webhook channel dicatat di log dan tidak
  menggagalkan deployment.
- Flag `DEPLOY_NOTIFICATIONS_ENABLED` (default `true`) bisa mematikan fitur.
- `docker-compose.yml` meneruskan env tersebut ke backend.

## Frontend

Tab **CI/CD** di detail project sekarang memiliki:

- Select **Cakupan aplikasi**: seluruh project atau satu aplikasi.
- Kolom **Cakupan** di tabel token.
- Dialog plaintext menampilkan cakupan token dan contoh curl endpoint baru.
- Snippet CI dan GitHub Actions memakai
  `/api/v1/deploy/webhook/<token>`.
- Panel **Webhook native GitHub / GitLab** berisi payload URL, header
  signature/secret, dan event yang diperlukan.
- Peringatan bahwa project multi-aplikasi perlu `application_id` pada mode CI.

## Contoh GitHub Actions

```yaml
- name: Deploy via InfraForge
  run: |
    curl -fsS -X POST "${{ secrets.INFRAFORGE_TRIGGER_URL }}" \
      -H "Content-Type: application/json" \
      -H "Idempotency-Key: ${{ github.run_id }}" \
      -d '{"branch":"${{ github.ref_name }}"}'
```

Isi `INFRAFORGE_TRIGGER_URL` dengan URL lengkap
`https://<host>/api/v1/deploy/webhook/<token>`. Untuk project multi-aplikasi,
tambahkan `application_id` di body atau gunakan token yang sudah di-scope ke
aplikasi.

## Verifikasi

### Backend

```bash
cd backend
uv run --no-dev pytest -q
uv run --no-dev ruff check app tests
uv run --no-dev mypy app
```

Hasil: **876 passed, 31 warnings**, ruff bersih, mypy **120 source file** tanpa
issue. Warnings yang tersisa berasal dari deprecation Starlette/passlib dan
warning lama test health-check, bukan dari fitur ini.

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

Hasil: build sukses; lint tetap 3 warning baseline (`only-export-components`
dan `set-state-in-effect`) yang tidak terkait perubahan ini.

### E2E

Harness yang dijalankan (tidak dikomit, berada di
`/tmp/opencode/ui-test/m7-deploy-webhook-e2e.cjs`) memakai Chrome CDP tanpa
puppeteer dan mock HTTP server untuk channel notifikasi. Hasil: **60/60 check
lulus**.

Cakupan E2E:

1. UI memuat tab CI/CD dan select cakupan berisi project + 2 aplikasi.
2. Pembuatan token aplikasi lewat UI, plaintext sekali, cakupan tabel, snippet
   endpoint baru, dan panduan GitHub/GitLab.
3. CI sederhana `202`, deployment `failed` (repo sengaja tidak valid), dan
   `trigger_source=ci_token`.
4. Idempotency CI, payload invalid `400`, token invalid `404`.
5. GitHub native: signature valid, project-wide menjadwalkan 2 aplikasi,
   duplicate `accepted=false`, signature invalid `401`, event non-push
   `accepted=false`.
6. GitLab native: secret valid, token aplikasi menjadwalkan 1 aplikasi,
   secret invalid `401`.
7. Notifikasi mock menerima pesan `queued` dan `failed` dengan payload aplikasi.
8. Endpoint legacy `/api/deploy/trigger/<token>` tetap `202`.
9. Audit `DEPLOY_WEBHOOK`: path `/v1/deploy/webhook/[redacted]`, username
   `deploy-token:*`, delivery/repository/commit, dan tidak ada token mentah.
10. Revoke token dari UI, status menjadi `Dicabut`, lalu webhook `404`.

Deployment E2E sengaja memakai repository `https://127.0.0.1:1/...` agar gagal
cepat. Yang diverifikasi adalah alur webhook, queue, status, audit, dan
notifikasi, bukan eksekusi Docker Compose aplikasi nyata.

## Batasan

- Commit SHA dari event hanya masuk audit; clone tetap mengambil HEAD branch
  saat deployment berjalan.
- Token ada di URL webhook. Gunakan HTTPS dan simpan sebagai secret; rotasi
  dengan membuat token baru lalu mencabut yang lama.
- Belum ada rate limiting khusus endpoint webhook; lindungi di reverse proxy
  bila endpoint terekspos publik.
- Notifikasi bergantung pada channel alert global; tidak ada channel khusus per
  project.
- Webhook native membutuhkan repository dan branch aplikasi yang sama persis
  setelah normalisasi URL.
