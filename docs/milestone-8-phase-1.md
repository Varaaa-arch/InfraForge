# Milestone 8 Fase 1 — Container Image Vulnerability Scanning

Fase ini menambahkan pemindaian kerentanan image container menggunakan
[Trivy](https://trivy.dev/) langsung dari dashboard InfraForge. Pengguna dapat
memicu scan, melihat riwayat, membuka detail CVE, dan memindai ulang image tanpa
meninggalkan halaman keamanan.

## Cakupan

- Model `image_scans` menyimpan satu baris per pemindaian. Rescan **membuat
  baris baru**, bukan menimpa hasil lama, sehingga perubahan temuan dapat
  dibandingkan.
- Ringkasan severity (`critical`, `high`, `medium`, `low`), total temuan,
  digest image, status scan, scanner, waktu, dan pemicu disimpan terstruktur.
- Detail CVE disimpan sebagai JSON ringkas (maksimum
  `IMAGE_SCAN_MAX_FINDINGS`, default 500) pada kolom `findings`.
- Project bersifat opsional. Jika diisi, scan hanya dapat diakses pemilik
  project atau admin.
- Pemindaian berjalan sinkron terhadap request (`asyncio.to_thread`) dengan
  timeout, sehingga event loop tetap responsif.
- Kegagalan scanner tidak menggagalkan request: scan tetap dibuat dengan status
  `failed` dan pesan error yang bisa ditampilkan di UI.
- Notifikasi alert dikirim ke channel aktif bila jumlah CRITICAL/HIGH melewati
  threshold yang dikonfigurasi.

## Izin & RBAC

Izin baru `image:scan` diberikan kepada **Admin** dan **Developer**. **Viewer**
hanya dapat melihat riwayat dan detail scan.

| Aksi | Admin | Developer | Viewer |
|---|---|---|---|
| Lihat riwayat/detail | Ya | Ya | Ya |
| Trigger scan | Ya | Ya | Tidak (403) |
| Rescan | Ya | Ya | Tidak (403) |

Visibilitas data:
- Admin melihat semua scan.
- Pengguna lain melihat scan miliknya sendiri atau scan yang terhubung ke
  project miliknya.

## API

Semua endpoint mengembalikan `ApiResponse` (`success`, `data`).

### `POST /image-scans`

```json
{
  "image_name": "nginx:1.27",
  "project_id": 12
}
```

`project_id` opsional. `image_name` divalidasi agar hanya berisi karakter
referensi image yang aman (tanpa spasi/opsi CLI). Response `201` berisi detail
scan. Jika Trivy tidak tersedia, timeout, atau output rusak, status response
tetap `201` dengan `data.status = "failed"`.

### `GET /image-scans`

Query opsional: `project_id`, `image` (pencarian substring), `limit` (1–200,
default 50), `offset`. Response:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

`items` tidak menyertakan daftar `findings` agar payload ringan.

### `GET /image-scans/{id}`

Mengembalikan detail scan beserta `findings`. Scan yang tidak dapat diakses
mengembalikan `404`.

### `POST /image-scans/{id}/rescan`

Membuat scan baru dengan image dan project yang sama, lalu menjalankan Trivy.
Response `201` berisi scan baru; riwayat lama tidak berubah.

Contoh temuan:

```json
{
  "cve_id": "CVE-2026-0001",
  "package": "openssl",
  "installed_version": "3.0.0",
  "fixed_version": "3.0.1",
  "severity": "critical",
  "title": "Contoh kerentanan",
  "target": "debian 12",
  "primary_url": "https://avd.aquasec.com/nvd/cve-2026-0001"
}
```

## Konfigurasi

| Env | Default | Keterangan |
|---|---|---|
| `TRIVY_PATH` | `trivy` | Path binary Trivy di backend |
| `TRIVY_CACHE_DIR` | cache Trivy | Direktori cache DB Trivy (Docker Compose memakai `/var/lib/trivy`) |
| `IMAGE_SCAN_TIMEOUT_SECONDS` | `180` | Timeout satu pemindaian |
| `IMAGE_SCAN_MAX_OUTPUT_BYTES` | `10485760` | Batas output JSON mentah |
| `IMAGE_SCAN_MAX_FINDINGS` | `500` | Jumlah finding yang disimpan per scan |
| `IMAGE_SCAN_CRITICAL_THRESHOLD` | `0` | Alert bila `critical_count >` nilai ini |
| `IMAGE_SCAN_HIGH_THRESHOLD` | `0` | Alert bila `high_count >` nilai ini |
| `IMAGE_SCAN_NOTIFICATIONS_ENABLED` | `true` | Kirim notifikasi ke channel alert |

Image backend Docker sudah memasang Trivy dan menyimpan cache DB di named
volume `trivy_cache`. Untuk pengembangan lokal, pasang binary Trivy di `PATH`
atau set `TRIVY_PATH` ke lokasi binary.

## Audit

Middleware allowlist mencatat:

- `IMAGE_SCAN` untuk `POST /image-scans`
- `IMAGE_SCAN_RESCAN` untuk `POST /image-scans/{id}/rescan`

Body request tidak disimpan. Referensi image dan project tidak ditulis ke pesan
audit secara eksplisit; detail scan tetap dapat ditelusuri dari tabel
`image_scans`.

## UI

Halaman baru **Keamanan** (`/security`) di section **Infrastructure**:

- Kartu ringkasan akumulasi Critical/High/Medium/Low dari scan terbaru.
- Form trigger scan: referensi image + pilihan project opsional.
- Filter pencarian dan severity, auto-refresh 20 detik.
- Tabel riwayat dengan badge status, badge severity, dan hitungan C/H/M/L.
- Dialog detail berisi digest, waktu, pemicu, error (jika gagal), ringkasan
  severity, dan tabel CVE dengan tautan referensi.
- Tombol **Pindai ulang** pada tabel dan dialog. Setelah rescan, dialog otomatis
  membuka hasil scan terbaru.

## Migrasi

Migrasi `e6b1f4c9a2d7_add_image_scans.py` membuat tabel `image_scans` dengan
`down_revision = "d4e6f8a1c2b3"` dan enum `image_scan_status`.

```bash
cd backend
uv run --no-dev alembic upgrade head
```

## Verifikasi

```bash
cd backend
uv run --no-dev pytest -q
uv run --no-dev ruff check app tests
uv run --no-dev mypy app

cd ../frontend
npm run build
npm run lint
```

Test baru `backend/tests/test_image_scan.py` mencakup parser Trivy, ringkasan
severity, batas finding, RBAC trigger/list/detail, visibilitas per pemilik,
validasi project, riwayat rescan, filter/pagination, audit allowlist, dan
notifikasi threshold.

Hasil verifikasi lokal:

- `pytest -q`: **935 passed**.
- `ruff check app tests` dan `mypy app`: lolos.
- `npm run build`: lolos; `npm run lint`: hanya 3 warning baseline komponen UI.
- `docker compose build backend frontend`: lolos.
- Binary Trivy di image backend: **0.76.2**.
- Uji nyata `trivy image alpine:3.20`: JSON valid, 1 result, 2 temuan pada
  vulnerability DB saat verifikasi.
- Uji API live di Docker Compose: trigger scan `alpine:3.20` selesai dengan
  severity `high` dan 2 finding, detail mengembalikan CVE, rescan membuat baris
  baru. Data uji dibersihkan setelah verifikasi.
- `alembic upgrade`/`downgrade` untuk migrasi baru berhasil.

## Batasan

- Scan berjalan sinkron; image besar atau registry lambat dapat menahan request
  hingga timeout. Untuk beban tinggi, pindahkan eksekusi ke worker ARQ pada
  fase berikutnya.
- Temuan CVE disimpan sebagai JSON pada baris scan; belum ada tabel
  `vulnerability_findings` terpisah untuk query CVE lintas scan.
- Image privat memerlukan kredensial registry yang tersedia untuk proses Trivy
  di host backend. Konfigurasi kredensial registry via UI belum disediakan.
- Trivy mengunduh/update vulnerability DB saat cache kosong. Scan pertama bisa
  lebih lambat dan membutuhkan akses internet.
- Notifikasi hanya dipicu oleh threshold CRITICAL/HIGH; kegagalan scanner tidak
  mengirim alert (status dan pesan error tetap tersimpan di riwayat).
