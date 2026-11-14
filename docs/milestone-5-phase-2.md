# Milestone 5 Fase 2 — Manajemen Konfigurasi & Rahasia (Env Vars & Secrets Manager)

Fase 2 membuka sisi konfigurasi & rahasia: environment variable per project
dengan penyimpanan terenkripsi (Fernet), secret masking, dan indikator
re-deploy.

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Permukaan UI | `/projects` (daftar project) + `/projects/:id` bertab (**Ringkasan**, **Environment Variables**) |
| Indikator re-deploy | Dihitung backend: `pending_redeploy` per env var (diubah setelah deployment terakhir) |
| Otorisasi reveal | Dialog konfirmasi + pencatatan audit log (tanpa endpoint verify-password baru) |
| Bulk import `.env` | Parser di frontend, kirim lewat bulk upsert yang sudah ada |
| Scope env var | Satu env var berlaku untuk **semua aplikasi** di project yang sama (`project_env_vars`) |

## Kontrak API

### `GET /projects/{project_id}/env` — list (masked) + status re-deploy

Respons berubah dari array menjadi objek agar sekaligus membawa konteks
deployment terakhir. Tidak ada consumer lain (CLI tidak memakai endpoint ini).

```json
{
  "success": true,
  "data": {
    "last_deployment_at": "2026-11-13T07:38:37.561546Z",
    "env_vars": [
      {
        "id": 7,
        "project_id": 6,
        "key": "DEMO_API_KEY",
        "masked_value": "abc****",
        "pending_redeploy": true,
        "created_at": "2026-11-13T12:38:37.573416Z",
        "updated_at": "2026-11-13T12:38:37.573416Z"
      }
    ]
  }
}
```

| Field | Arti |
|---|---|
| `last_deployment_at` | `started_at` deployment terakhir untuk seluruh aplikasi di project (`null` bila belum pernah deploy) |
| `masked_value` | 3 karakter pertama + `****` (nilai pendek ≤2 karakter → `****` penuh) |
| `pending_redeploy` | `true` bila `updated_at` env var > `last_deployment_at` → container yang sedang jalan belum memakai nilai baru |

### `PATCH /projects/{project_id}/env/{env_id}` — ubah nilai satu variabel

```json
// Request
{ "value": "postgres://user:pass@host/db" }

// Response (200) — masked, tidak mengembalikan plaintext
{
  "success": true,
  "data": {
    "id": 7,
    "project_id": 6,
    "key": "DEMO_API_KEY",
    "masked_value": "pos****",
    "pending_redeploy": true,
    "created_at": "2026-11-13T12:38:37.573416Z",
    "updated_at": "2026-11-14T08:12:00.000000Z"
  }
}
```

| Status | Kondisi |
|---|---|
| `200` | Nilai diperbarui (dienkripsi ulang dengan Fernet) |
| `404` | Env var atau project tidak ditemukan / bukan milik user |
| `422` | Value kosong atau mengandung newline / null byte |

Key tidak dapat diubah lewat PATCH (gunakan bulk upsert dengan key baru +
hapus key lama).

### `GET /projects/{project_id}/env/{env_id}` — reveal

Tidak berubah, tetapi sekarang mencatat audit log
`[REVEAL_ENV_VAR] user=… project_id=… env_id=…`.

### `POST /projects/{project_id}/env` — bulk upsert (dipakai Bulk Import)

```json
{ "env_vars": [{ "key": "DATABASE_URL", "value": "postgres://…" }] }
```

Respons tetap `{ "summary": { "created": n, "updated": n, "total": n }, "env_vars": [...] }`.
Key dinormalisasi uppercase; key yang sudah ada akan **di-update**.

### `DELETE /projects/{project_id}/env/{env_id}` — hapus

Tidak berubah (`204`-style body `{ "message": … }`, status `200`).

### Endpoint pendukung (dipakai UI, tidak berubah)

| Method | Path | Pakai untuk |
|---|---|---|
| `GET` | `/projects` | Daftar project |
| `GET` | `/projects/{id}` | Detail project |
| `GET` | `/applications?project_id={id}` | Daftar aplikasi read-only di tab Ringkasan |

## Aturan Bulk Import `.env`

Parsing dilakukan di frontend (`src/lib/env-parser.ts`), hasil akhir dikirim
lewat bulk upsert:

| Baris | Hasil |
|---|---|
| `KEY=value` | Import (key uppercase) |
| `export KEY=value` | Import (prefix `export ` dibuang) |
| `# komentar` | Diabaikan |
| Baris kosong | Diabaikan |
| `KEY="value"` / `KEY='value'` | Import, tanda kutip dilepas |
| `KEY` (tanpa `=`) | Lewat — "Format harus KEY=VALUE" |
| `1KEY=value` | Lewat — key tidak valid |
| `KEY=` (value kosong) | Lewat — "Value kosong" |
| `KEY=a` lalu `KEY=b` | Baris pertama wins, baris kedua lewat (duplikat) |

Key yang sudah ada di project ditandai **update** di preview, key baru
ditandai **baru**. Tidak ada variabel yang dihapus oleh bulk import.

## Work package

| Paket | Isi | Status |
|---|---|---|
| 2.1 | Kontrak API, tipe TS, API client, parser `.env` | ✅ selesai |
| 2.2 | Backend: `PATCH` env var, `pending_redeploy`, audit reveal | ✅ selesai |
| 2.3 | Halaman `/projects` (daftar project) | ✅ selesai |
| 2.4 | Halaman `/projects/:id` bertab (Ringkasan + Environment Variables) | ✅ selesai |
| 2.5 | Bulk Import `.env` | ✅ selesai |
| 2.6 | Verifikasi, regresi Milestone 4, dokumentasi | ✅ selesai |

## Pengujian

### Backend

```
pytest               → 683 passed, 0 failed   (sebelum Fase 2: 672 passed)
ruff check app tests → 10 temuan (baseline, tidak bertambah)
mypy app             → 3 temuan (baseline, app/worker.py)
```

Test baru di `tests/test_env_redeploy.py` (11 test): `PATCH` sukses/404/404-owner/
422, `last_deployment_at` null & terisi, `pending_redeploy` benar/salah/terisolasi
per project, `PATCH` menandai env var perlu re-deploy, serta audit
`REVEAL_ENV_VAR` dan `UPDATE_ENV_VAR`.

Test lama di `tests/test_env.py` (5 test) diperbarui mengikuti bentuk response
list yang baru (`data.env_vars` + `data.last_deployment_at`).

### Frontend

```
npm run build → sukses
npm run lint  → 3 warning (baseline: fast-refresh & efek React)
```

### E2E (Playwright, Chrome headless)

| Skrip | Cakupan | Hasil |
|---|---|---|
| `env-vars-e2e.cjs` | Buka project → tab Ringkasan (2 aplikasi) → tab Env Vars (2 var tersamar) → banner re-deploy → reveal (konfirmasi → nilai terlihat → sembunyikan) → edit → tambah → hapus | **16/16** |
| `bulk-import-e2e.cjs` | Bulk import `.env` (3 variabel valid + 3 baris tidak valid) → preview dengan nilai tersamar → alasan baris dilewati → simpan (3 baru) → hapus var uji | **10/10** |
| `milestone4-regression.cjs` | Regresi Milestone 4: kartu Overview, health server, 4 grafik + range 6h, panel Top container, tabel alert, Logs, live tail WebSocket | **30/30** |
| `servers-e2e.cjs` | Regresi Fase 1: halaman Servers (CRUD server uji) | **15/15** |
| `containers-e2e.cjs` | Regresi Fase 1: halaman Containers (filter, Inspect 4 tab, lifecycle stop → start → restart) | **20/20** |

Tidak ada `pageerror` pada seluruh skenario.

### Data nyata

```
GET /projects/6/env →
  last_deployment_at : 2026-11-13T07:38:37Z
  DEMO_API_KEY  masked=sk-****  pending_redeploy=true
  LOG_LEVEL     masked=inf****  pending_redeploy=true

PATCH /projects/6/env/7 {"value": "..."} → 200, masked=dem****, pending_redeploy=true
GET  /projects/6/env/7 (reveal)    → 200, plaintext + audit [REVEAL_ENV_VAR]
```

## Catatan operasional

- **Env var ter-scope project**: satu variabel dipakai semua aplikasi di project
  tersebut, sehingga `pending_redeploy` berlaku untuk seluruh app di project.
- **Bulk import tidak menghapus apa pun**: key yang sudah ada diperbarui, key
  baru ditambahkan, dan baris tidak valid dilewati dengan alasannya.
- **Reveal dicatat di audit log** (`REVEAL_ENV_VAR`) lengkap dengan user, project,
  dan key — nilai itu sendiri tidak ikut dicatat.
- **Nilai yang ter-reveal hanya hidup di memori browser** dan kembali tersamar
  saat disembunyikan atau saat meninggalkan tab.

## Di luar scope Fase 2

CRUD project & application (backend sudah siap, UI-nya di Fase 3) · trigger
deploy dari UI · rotasi `ENCRYPTION_KEY` · export env var ke file.
