# Milestone 8 Fase 3 — Security Hardening Posture, Audit & E2E Penutup

Fase ini menyatukan hasil pemindaian CVE, status sertifikat TLS, dan pemeriksaan
konfigurasi container menjadi satu **posture keamanan** yang dapat dipantau dari
dashboard. Fase ini juga menutup Milestone 8 dengan audit akses, pengujian E2E
Playwright, dan seed data deterministik.

## Cakupan

- Endpoint agregat `GET /security/posture` untuk seluruh peran yang login.
- Skor posture 0–100 dengan tiga level: `aman`, `perlu_perhatian`, `berisiko`.
- Kartu **Posture Keamanan** di dashboard dan halaman **Keamanan**.
- Pemeriksaan container dari `container.attrs`:
  - privileged mode,
  - user root/default,
  - root filesystem writable,
  - capability `ALL` tidak di-drop,
  - opsi `no-new-privileges` tidak aktif.
- Audit akses posture (`SECURITY_POSTURE_READ`) dan audit aksi yang sudah ada:
  scan image, rescan, perubahan target/kebijakan, dan cek TLS.
- Seed E2E `backend/scripts/seed_m8_e2e.py` + skenario
  `frontend/e2e/milestone-8.spec.ts`.

## Sumber Data

Posture dihitung **on demand** dari data yang sudah dimiliki platform. Tidak ada
tabel baru dan tidak ada migrasi Alembic.

| Kategori | Sumber | Yang dihitung |
|---|---|---|
| Image | `image_scans` | Jumlah scan, completed/failed, CVE critical/high/medium/low, image terdampak, finding CVE teratas |
| TLS | `tls_domains` | Total, enabled, healthy, expiring, expired, invalid, error, pending |
| Container | Docker `container.attrs` | Container berjalan, privileged, root user, writable rootfs, cap-drop, no-new-privileges |

Container yang diperiksa untuk posture adalah container berstatus `running`.
Jika Docker daemon tidak dapat diakses, kategori container ditandai
`available=false` dengan pesan error, tetapi endpoint tetap mengembalikan data
image dan TLS.

## Formula Skor

Skor dimulai dari 100 lalu dikurangi penalti per kategori. Setiap kategori
dibatasi agar satu jenis masalah tidak menghabiskan seluruh skor.

| Kategori | Penalti | Batas |
|---|---|---|
| Image | `critical*4 + high*1 + failed*2` | 40 |
| TLS | `expired*15 + invalid*10 + error*8 + expiring*3 + pending*1` | 35 |
| Container | `privileged*20 + root_user*8 + writable_rootfs*4 + missing_cap_drop_all*3 + missing_no_new_privileges*2` | 35 |

Level:

- `aman` — skor ≥ 80.
- `perlu_perhatian` — skor 50–79.
- `berisiko` — skor < 50.

Formula sengaja sederhana dan deterministik agar mudah diuji. Bobot dapat
disesuaikan setelah review tanpa mengubah kontrak API.

## API

### `GET /security/posture`

Butuh autentikasi. Semua peran memiliki izin `security:read`.

```json
{
  "success": true,
  "data": {
    "score": 22,
    "level": "berisiko",
    "generated_at": "2026-11-23T10:00:00Z",
    "images": {
      "total_scans": 4,
      "completed": 3,
      "failed": 1,
      "critical_count": 3,
      "high_count": 1,
      "medium_count": 1,
      "low_count": 0,
      "affected_images": 2,
      "latest_scanned_at": "2026-11-23T09:55:00Z"
    },
    "tls": {
      "total": 4,
      "enabled": 4,
      "healthy": 1,
      "expiring": 1,
      "expired": 1,
      "invalid": 1,
      "error": 0,
      "pending": 0
    },
    "containers": {
      "available": true,
      "total": 11,
      "running": 11,
      "privileged": 1,
      "root_user": 10,
      "writable_rootfs": 11,
      "missing_cap_drop_all": 11,
      "missing_no_new_privileges": 10,
      "error_message": null
    },
    "checks": [
      {
        "key": "image_critical",
        "category": "image",
        "title": "Temuan CVE critical",
        "status": "fail",
        "severity": "critical",
        "detail": "3 temuan critical pada image.",
        "count": 3
      }
    ],
    "findings": [
      {
        "category": "image",
        "severity": "critical",
        "title": "CVE-2026-4242 (critical)",
        "detail": "openssl pada image e2e/unsafe:1.",
        "resource": "e2e/unsafe:1"
      }
    ]
  }
}
```

`checks` berisi daftar pemeriksaan dengan status `pass`, `warn`, `fail`, atau
`unknown`. `findings` berisi maksimum 20 temuan teratas, diurutkan berdasarkan
severity. Container findings hanya menyebut nama container dan jenis masalah;
tidak mengembalikan env var atau isi filesystem.

## RBAC

Izin baru `security:read` diberikan kepada **Admin**, **Developer**, dan
**Viewer**. Viewer tetap dapat memantau posture, CVE, dan status TLS secara
read-only.

| Aksi | Admin | Developer | Viewer |
|---|---|---|---|
| Lihat posture/CVE/TLS | Ya | Ya | Ya |
| Trigger scan / rescan | Ya | Ya | Tidak (403) |
| Tambah/ubah/hapus target TLS | Ya | Ya | Tidak (403) |
| Cek ulang TLS | Ya | Ya | Tidak (403) |
| Ubah kebijakan container | Ya | Ya | Tidak (403) |

Backend tetap menegakkan izin walaupun tombol UI disembunyikan/dinonaktifkan.

## Audit

Middleware allowlist sudah mencatat aksi keamanan berikut:

- `IMAGE_SCAN` — `POST /image-scans`
- `IMAGE_SCAN_RESCAN` — `POST /image-scans/{id}/rescan`
- `TLS_DOMAIN_CREATE` / `TLS_DOMAIN_UPDATE` / `TLS_DOMAIN_DELETE`
- `TLS_DOMAIN_CHECK` — `POST /tls-domains/{id}/check`
- `CONTAINER_POLICY_UPDATE` / `CONTAINER_POLICY_DELETE`

Fase 3 menambahkan:

- `SECURITY_POSTURE_READ` — `GET /security/posture`

Body request tidak disimpan. Audit akses posture membantu menelusuri siapa yang
membuka ringkasan keamanan, sementara aksi mutasi tetap tercatat dengan detail
resource yang relevan.

## UI

Komponen `SecurityPostureCard` dipakai di dua tempat:

- **Overview** (`/`) — kartu posture di bawah statistik utama.
- **Keamanan** (`/security`) — kartu posture di atas ringkasan CVE.

Kartu menampilkan:

- skor dan level dengan warna status,
- ringkasan CVE image, status TLS, dan container,
- temuan teratas beserta severity/resource,
- pemeriksaan yang belum lulus,
- tombol muat ulang dan tautan ke halaman Keamanan/TLS.

Auto-refresh 30 detik. Viewer melihat data yang sama tanpa tombol mutasi.
Tombol mutasi pada halaman Keamanan/TLS tetap digate oleh `canDeploy`
(Admin/Developer).

## E2E Playwright

Seed `backend/scripts/seed_m8_e2e.py` membuat data terisolasi:

- user `e2e_m8_admin`, `e2e_m8_dev`, `e2e_m8_viewer` (password `e2e-password`),
- scan aman, scan dengan CVE critical/high, scan gagal, dan scan milik Viewer,
- target TLS healthy/expiring/expired/invalid beserta riwayat pemeriksaan.

Data lama dengan username/host seed yang sama dihapus lebih dulu, sehingga
skenario idempoten.

`frontend/e2e/milestone-8.spec.ts` memverifikasi:

- kartu posture tampil di dashboard dan halaman Keamanan,
- CVE dari seed tampil di detail scan,
- status TLS expired dan pesan error tampil di tabel/detail,
- audit `SECURITY_POSTURE_READ` dan `TLS_DOMAIN_CHECK` tercatat,
- scan nyata `alpine:3.20` dijalankan bila Trivy tersedia; jika tidak, skenario
  tetap lulus dengan data seed,
- Viewer dapat membaca posture/CVE/TLS tetapi tidak melihat tombol mutasi dan
  mendapat `403` saat memanggil API scan/TLS,
- tidak ada page error.

Perintah:

```bash
docker compose build backend frontend
docker compose up -d backend frontend
docker compose exec -T backend uv run --no-dev python scripts/seed_m8_e2e.py
cd frontend
PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 npx playwright test
```

## Verifikasi

Lokal:

- `pytest -q`: **964 passed** (9 test posture baru).
- `ruff check app tests scripts`: lolos.
- `mypy app`: lolos.
- `npm run build`: lolos.
- `npm run lint`: hanya 3 warning baseline komponen UI/hook.
- Playwright: **2 passed** (`milestone-7.spec.ts` dan `milestone-8.spec.ts`).
- Docker Compose backend/frontend dibangun ulang dan dijalankan.
- Scan nyata `alpine:3.20` dengan Trivy di container selesai (`completed`,
  0 critical, 2 high).
- Seed E2E berhasil dan idempoten.

## Batasan

- Posture dihitung saat request; belum ada worker periodik yang menyimpan
  snapshot historis.
- Skor adalah heuristik, bukan standar compliance (CIS/PCI) dan belum
  memperhitungkan seluruh hardening Docker.
- Pemeriksaan container hanya memakai field umum `container.attrs`; container
  yang berhenti tidak dinilai.
- Jika Docker tidak tersedia, skor tidak memasukkan penalti container dan
  kategori container ditandai `unknown`.
- Agregasi posture bersifat global platform, bukan per-project/per-owner.
- Audit pembacaan posture dapat menambah volume audit log bila dashboard
  dibiarkan terbuka dalam waktu lama.
