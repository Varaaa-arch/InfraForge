# Milestone 7 Fase 4 — Token Rotation, Security Alerts & Playwright E2E

Fase ini menutup sisa DoD Milestone 7: rotasi deployment token tanpa membuat
token baru, notifikasi keamanan untuk aktivitas token dan webhook yang ditolak,
serta skenario E2E Playwright yang mencakup token → webhook → riwayat → rollback
→ branch filter → live log.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 7.4.1 | Backend: rotasi token in-place, guard revoked/expired, audit `DEPLOY_TOKEN_ROTATE` | `c7592a7` |
| 7.4.2 | Backend: notifikasi security token lifecycle dan outcome webhook | `c7592a7` |
| 7.4.3 | Frontend: API + dialog rotasi dan modal plaintext baru | `a494392` |
| 7.4.4 | E2E: Playwright, seed deterministik, dokumentasi | `c7592a7`, `a494392`, commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Semantik rotasi | Update token yang sama in-place; ID, nama, cakupan aplikasi, dan expiry dipertahankan |
| Expiry baru | Hanya berubah bila request mengirim `expires_in_days` |
| Token nonaktif | Rotasi token revoked/expired ditolak `409`; pengguna harus membuat token baru |
| Plaintext | Token baru dikembalikan sekali pada response rotasi dan tidak pernah disimpan |
| Notifikasi security | Memakai channel alert existing; tidak membuat baris `alert_events` baru |
| Cakupan alert | Token create/rotate/revoke dan semua outcome webhook kecuali `scheduled` |
| Duplikasi notifikasi | `scheduled` dilewati karena notifikasi deployment queued sudah dikirim |
| E2E | Playwright memakai Chrome sistem (`channel: "chrome"`), tanpa download browser |
| Data E2E | Seed deterministik `e2e_m7` membuat project, aplikasi, token flow, dan live log sendiri |
| Isolasi E2E | Seed menghapus user `e2e_m7` (cascade data miliknya) sebelum membuat ulang data |

## Backend

### Endpoint rotasi

| Method | Path | Status | Keterangan |
|---|---|---|---|
| `POST` | `/projects/{project_id}/deploy-tokens/{token_id}/rotate` | `200` | Token baru plaintext dikembalikan sekali |
| | | `404` | Project/token tidak ditemukan atau bukan milik user |
| | | `409` | Token sudah dicabut atau kedaluwarsa |

Body opsional:

```json
{
  "expires_in_days": 30
}
```

Tanpa body, masa berlaku lama dipertahankan. Token lama langsung tidak berlaku
setelah response sukses; deployment yang sedang berjalan tidak dibatalkan.

### File utama

| File | Peran |
|---|---|
| `app/schemas/deployment_token.py` | `DeploymentTokenRotate` |
| `app/repositories/deployment_token_repository.py` | Update hash/prefix/expiry in-place |
| `app/services/deployment_token_service.py` | `_generate_token`, `rotate_token`, guard token nonaktif |
| `app/api/deploy_tokens.py` | Endpoint rotate, background notification, audit webhook outcomes |
| `app/middleware/audit_middleware.py` | Rule `DEPLOY_TOKEN_ROTATE` |
| `app/services/deploy_security_notification_service.py` | Alert token lifecycle dan webhook outcome |
| `tests/test_deploy_tokens.py` | Rotasi, expiry, revoked/expired, non-owner, audit |
| `tests/test_deploy_security_notifications.py` | Severity, project context, disable flag, dedupe scheduled |
| `scripts/seed_m7_e2e.py` | Seed E2E dan kontrol append/finish live log |

### Audit

| Action | Resource | Detail |
|---|---|---|
| `DEPLOY_TOKEN_ROTATE` | `deploy_token` | `project_id`, `id` |

Path audit tidak memuat token mentah. Token plaintext juga tidak masuk detail
audit maupun log notifikasi.

### Notifikasi security

| Event | Alert name | Severity |
|---|---|---|
| Token dibuat | `DeployTokenCreated` | `info` |
| Token dirotasi | `DeployTokenRotated` | `info` |
| Token dicabut | `DeployTokenRevoked` | `warning` |
| Webhook ditolak/diabaikan | `DeployWebhookRejected` | `info`/`warning` |

Outcome webhook `invalid_token`, `invalid_signature`, `invalid_payload`,
`invalid_target`, `no_target`, dan `conflict` memakai `warning`.
`duplicate`, `ignored_event`, `no_match`, `locked`, dan `partial` memakai
`info`. `scheduled` tidak dikirim oleh service security.

Notifikasi dijadwalkan dari audit middleware setelah response, sehingga tetap
terkirim untuk jalur error seperti token tidak valid atau signature salah yang
tidak melewati response normal endpoint. Pengiriman bersifat best-effort:
channel yang gagal dijangkau dicatat di log dan tidak menggagalkan request
utama.

## Frontend

Tab CI/CD menambahkan:

- Tombol **Rotasi** pada token aktif.
- Dialog konfirmasi yang menjelaskan token lama langsung tidak berlaku.
- Modal plaintext baru dengan judul dan pesan khusus rotasi.
- Feedback sukses/gagal setelah rotasi.
- Tombol rotasi dan revoke tetap hanya tersedia untuk pengguna yang boleh
  mengelola token.

## E2E Playwright

Konfigurasi:

- `frontend/playwright.config.ts`
- Base URL default `http://127.0.0.1:5173`
- `channel: "chrome"`
- Satu worker, tanpa web server otomatis
- Spec: `frontend/e2e/milestone-7.spec.ts`

Persiapan:

```bash
docker compose up -d --build backend frontend
docker compose exec -T backend uv run --no-dev python scripts/seed_m7_e2e.py
cd frontend
npm run test:e2e
```

Cakupan skenario:

1. Login sebagai admin owner `e2e_m7`.
2. Deep link webhook GitHub mengarah ke halaman hooks repository.
3. Buat token dengan cakupan aplikasi `worker`.
4. Rotasi token; plaintext baru berbeda dan token lama ditolak `404`.
5. Ubah branch filter aplikasi `worker` dari `main` menjadi `release`.
6. Webhook push `main` diterima `202` dengan `accepted=false`.
7. Webhook push `release` diterima `202` dengan `accepted=true`.
8. Riwayat menampilkan deployment webhook branch `release`.
9. Rollback deployment sukses lama `v1.0.0` dan badge Rollback muncul.
10. Live log menampilkan status `Live`, baris baru muncul real-time, lalu
    berubah `Selesai` setelah deployment selesai.
11. Log historis dapat dibuka ulang.
12. Audit `DEPLOY_WEBHOOK` memuat `no_match` dan `scheduled`; audit
    `DEPLOY_TOKEN_ROTATE` tercatat.
13. Tidak ada page error selama skenario.

## Verifikasi

```bash
cd backend
uv run --no-dev pytest -q          # 920 passed
uv run --no-dev ruff check app tests
uv run --no-dev mypy app

cd ../frontend
npm run build
npm run lint
npm run test:e2e                   # 1 passed
```

## Batasan

- Rotasi tidak mengubah nama, cakupan aplikasi, atau pemilik token.
- Token yang sudah dicabut tidak dapat diaktifkan kembali lewat rotasi.
- Notifikasi security bergantung pada channel alert aktif dan flag
  `DEPLOY_NOTIFICATIONS_ENABLED`.
- E2E membutuhkan Docker Compose berjalan, Chrome sistem, dan akses ke
  `docker compose`; bukan pengganti unit/integration test backend.
- Seed E2E bersifat destruktif hanya untuk user `e2e_m7` dan datanya.
