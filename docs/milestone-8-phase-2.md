# Milestone 8 Fase 2 — TLS/SSL Domain Certificate Monitoring

Fase ini menambahkan pemantauan sertifikat TLS/SSL dari dashboard InfraForge.
Pengguna dapat mendaftarkan host/port reverse proxy, melihat status expiry dan
validitas, membuka riwayat pemeriksaan, serta memicu recheck tanpa meninggalkan
halaman **TLS / SSL**.

## Cakupan

- Tabel `tls_domains` menyimpan konfigurasi target: label, host, port, status
  aktif, ambang warning, dan metadata sertifikat terakhir.
- Tabel `tls_domain_checks` menyimpan riwayat immutable setiap pemeriksaan.
- Inspeksi membaca issuer, subject, protocol, `notBefore`/`notAfter`, sisa hari,
  dan status verifikasi.
- Status yang digunakan:
  - `pending` — belum pernah diperiksa.
  - `healthy` — sertifikat valid, chain terverifikasi, dan di luar ambang warning.
  - `expiring` — valid tetapi sisa masa berlaku ≤ `warning_days`.
  - `expired` — `notAfter` sudah lewat.
  - `invalid` — belum berlaku, self-signed, hostname mismatch, atau verifikasi
    chain gagal.
  - `error` — koneksi/handshake/DNS gagal atau timeout.
- Pemeriksaan pertama dijalankan saat create kecuali `check_now=false`.
- Cache in-memory ber-TTL mencegah koneksi berulang untuk target yang sama;
  recheck manual selalu melewati cache.
- Notifikasi best-effort dikirim ke channel alert aktif saat status bermasalah,
  dengan cooldown per status agar tidak spam.

## Keputusan Desain

### Host/port, bukan URL

API menerima hostname atau IP literal dan port terpisah. Skema/path tidak
diterima; ini menghindari parsing URL yang ambigu dan membuat target mudah
divalidasi. Hostname dinormalisasi ke lowercase dan trailing dot dihapus.
Host/port bersifat unik.

### Dua handshake

1. Handshake pertama memakai `ssl.CERT_NONE` agar detail sertifikat tetap bisa
   dibaca walau sertifikat kedaluwarsa/self-signed.
2. Jika metadata dasar lolos (waktu valid, bukan self-signed, hostname cocok),
   handshake kedua memakai context default `ssl.create_default_context()` untuk
   memverifikasi chain dan hostname.

Dengan pendekatan ini UI tetap bisa menampilkan tanggal kedaluwarsa dan issuer
untuk sertifikat yang bermasalah, sementara status `healthy` hanya diberikan
bila verifikasi standar berhasil.

### Cache

Cache disimpan di memori proses backend, key `host:port:warning_days`, TTL
default 300 detik. Cache bersifat best-effort dan hilang saat restart; ini
cukup untuk mengurangi koneksi berulang, bukan pengganti worker monitoring
terjadwal.

### Proteksi SSRF

Secara default target yang berupa IP privat/loopback/link-local/reserved
ditolak. Hostname juga di-resolve dan ditolak bila seluruh/any address-nya
non-publik. Untuk target internal (mis. reverse proxy di jaringan Docker),
set `TLS_DOMAIN_ALLOW_PRIVATE_IP=true`. Aktifkan hanya bila backend memang
dipercaya untuk mengakses jaringan internal.

### Alert

- `expired` → severity `critical`.
- `expiring`, `invalid`, `error` → severity `warning`.
- Alert hanya dikirim bila status berubah, belum pernah dikirim, atau cooldown
  `TLS_ALERT_COOLDOWN_SECONDS` sudah lewat.
- Bila tidak ada channel aktif, status tetap tersimpan dan percobaan alert
  berikutnya bisa dilakukan.

## Izin & RBAC

Izin baru `tls_domain:write` diberikan kepada **Admin** dan **Developer**.
**Viewer** hanya dapat melihat daftar, detail, dan riwayat.

| Aksi | Admin | Developer | Viewer |
|---|---|---|---|
| Lihat daftar/detail/riwayat | Ya | Ya | Ya |
| Tambah target | Ya | Ya | Tidak (403) |
| Ubah/hapus target | Ya | Ya | Tidak (403) |
| Periksa ulang | Ya | Ya | Tidak (403) |

## API

Semua endpoint mengembalikan `ApiResponse` (`success`, `data`).

### `POST /tls-domains`

```json
{
  "name": "Website utama",
  "host": "example.com",
  "port": 443,
  "enabled": true,
  "warning_days": 30,
  "check_now": true
}
```

Response `201` berisi detail target + 20 riwayat terakhir. Duplikat host/port
mengembalikan `409`. Host tidak valid atau IP privat mengembalikan `422`. Jika
pemeriksaan gagal (timeout/DNS), target tetap dibuat dengan status `error`.

### `GET /tls-domains`

Query opsional: `search` (host/label), `status`, `enabled`, `limit` (1–200),
`offset`.

```json
{
  "items": [],
  "total": 0
}
```

### `GET /tls-domains/{id}`

Mengembalikan detail target beserta maksimum 20 pemeriksaan terakhir.

### `PATCH /tls-domains/{id}`

Field opsional: `name`, `host`, `port`, `enabled`, `warning_days`. Perubahan
host/port memicu pemeriksaan ulang otomatis. Perubahan `warning_days` saja
menghitung ulang status dari sisa hari yang sudah tersimpan tanpa koneksi baru.

### `DELETE /tls-domains/{id}`

Menghapus target dan seluruh riwayatnya (cascade).

### `POST /tls-domains/{id}/check`

Memaksa koneksi TLS baru, menyimpan hasil ke riwayat, dan mengembalikan detail
terbaru. Response `403` untuk Viewer.

### `GET /tls-domains/{id}/checks`

Riwayat pemeriksaan; query `limit` 1–200 (default 50).

## Konfigurasi

| Env | Default | Keterangan |
|---|---|---|
| `TLS_DOMAIN_CHECK_TIMEOUT_SECONDS` | `10` | Timeout koneksi/handshake per fase |
| `TLS_DOMAIN_CACHE_TTL_SECONDS` | `300` | TTL cache inspeksi; `0` menonaktifkan cache |
| `TLS_DOMAIN_EXPIRY_WARNING_DAYS` | `30` | Default warning bila target tidak menentukan |
| `TLS_DOMAIN_MAX_TARGETS` | `50` | Batas jumlah target |
| `TLS_DOMAIN_ALLOW_PRIVATE_IP` | `false` | Izinkan target IP privat/loopback |
| `TLS_NOTIFICATIONS_ENABLED` | `true` | Kirim alert status bermasalah |
| `TLS_ALERT_COOLDOWN_SECONDS` | `86400` | Cooldown alert untuk status yang sama |

## Audit

Middleware allowlist mencatat:

- `TLS_DOMAIN_CREATE` — `POST /tls-domains`
- `TLS_DOMAIN_UPDATE` — `PATCH /tls-domains/{id}`
- `TLS_DOMAIN_DELETE` — `DELETE /tls-domains/{id}`
- `TLS_DOMAIN_CHECK` — `POST /tls-domains/{id}/check`

Body tidak disimpan. Detail target dapat ditelusuri dari tabel `tls_domains`.

## UI

Halaman **TLS / SSL** (`/tls-domains`) di section **Infrastructure**:

- Kartu ringkasan: sehat, segera kedaluwarsa, bermasalah, belum diperiksa.
- Form tambah/ubah target (label, host, port, warning days, aktif, check now).
- Filter pencarian dan status, auto-refresh 60 detik.
- Tabel target: host:port, status + pesan error, expiry/sisa hari, issuer,
  waktu cek terakhir.
- Aksi: detail, recheck, ubah, hapus (dengan konfirmasi).
- Dialog detail: badge status/trust, metadata sertifikat, error, dan riwayat
  pemeriksaan.
- Tombol mutasi disembunyikan untuk Viewer; backend tetap menolak 403.

## Migrasi

Migrasi `a1f2b3c4d5e6_add_tls_domains.py` membuat tabel `tls_domains`,
`tls_domain_checks`, enum `tls_domain_status`, unique constraint host+port, dan
index yang diperlukan. `down_revision = "e6b1f4c9a2d7"` (Fase 1).

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

Test baru `backend/tests/test_tls_domain.py` mencakup:

- Sertifikat sehat, expiring, expired, self-signed, hostname mismatch,
  verifikasi gagal, timeout, dan connection error.
- Cache TTL, proteksi IP privat, dan override env.
- Create/list/detail/update/check/delete, duplikat, batas target, validasi host.
- RBAC Viewer/Developer/Admin, audit allowlist.
- Alert terkirim dan deduplikasi cooldown.

Hasil verifikasi lokal:

- `pytest -q`: **955 passed** (termasuk 20 test TLS baru).
- `ruff check app tests` dan `mypy app`: lolos.
- `npm run build`: lolos; `npm run lint`: hanya 3 warning baseline komponen UI.
- Inspeksi nyata `example.com:443`: status `healthy`, trusted, TLSv1.3,
  issuer Cloudflare, sisa 33 hari.
- Migrasi `a1f2b3c4d5e6`: `upgrade` dan `downgrade` berhasil.
- Docker Compose: backend & frontend berhasil dibangun ulang, migrasi dijalankan,
  lalu API live diuji: create `example.com` → `201 healthy`, recheck → `200`
  dengan 2 riwayat, target `127.0.0.1` → `422` (SSRF guard), delete → `200`.
  Data dan user uji dibersihkan setelah verifikasi.

## Batasan

- Pemeriksaan hanya berjalan saat create, update host/port, atau recheck manual;
  belum ada scheduler periodik. Auto-refresh UI hanya memuat data, bukan
  memeriksa sertifikat.
- Cache bersifat in-memory per proses, sehingga multi-worker/replika memiliki
  cache terpisah dan hilang saat restart.
- Pemeriksaan berjalan sinkron di thread; target lambat dapat menahan request
  hingga timeout (dua handshake).
- Hostname wildcard didukung untuk pola `*.example.com`, tetapi validasi
  hostname mengikuti aturan sederhana (belum mendukung IPv6 literal atau IDN
  punycode khusus).
- Notifikasi dievaluasi pada saat pemeriksaan; belum ada alert resolution
  terpisah saat sertifikat kembali sehat.
- Data target tidak di-scope per project; semua user yang login dapat melihat
  daftar target.
