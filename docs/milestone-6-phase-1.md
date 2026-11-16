# Milestone 6 Fase 1 — Multi-Channel Alert & Webhook Notifications

Fase ini membuat tim tidak perlu terus menatap dashboard: alert dikirim otomatis
ke Discord, Telegram, atau Slack sesuai tingkat keparahan. Pengaturan channel
dipindahkan ke **Settings → Notifikasi**, dan setiap channel punya tombol
**Test notifikasi** untuk memastikan konfigurasi benar sebelum dipakai.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 6.1 | Backend: channel Slack, kolom `min_severity`, routing severity, test notification ber-severity | `b93fd61` |
| 6.2 | Frontend: alert destination di Settings → Notifikasi + ringkasan di `/alerts` | `a97ef59` |
| 6.3 | Prometheus: 3 aturan severity `warning`; akses host untuk E2E webhook | `21580f4` |
| 6.4 | Verifikasi menyeluruh + dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Lokasi pengelolaan | Settings → Notifikasi. Halaman `/alerts` hanya menampilkan ringkasan dan tautan |
| Routing severity | Setiap channel punya `min_severity`; backend memfilter event sebelum mengirim |
| Peringkat severity | `info` < `warning` < `critical`; severity tak dikenal diperlakukan `info` |
| Slack | Incoming Webhook URL; payload Block Kit dengan `attachments.color` |
| Penyimpanan kredensial | Webhook URL dan bot token dienkripsi Fernet; response API hanya boolean `has_*` |
| Test notification | Memakai `min_severity` channel sebagai default; body `{"severity": ...}` opsional |
| Sumber notifikasi | Alertmanager mengirim semua alert ke satu webhook backend; filter dilakukan backend |
| Database enum | Nilai `slack` ditambahkan ke enum PostgreSQL; downgrade tidak menghapus nilai enum |

## Migrasi

`backend/alembic/versions/9c4e1f7a2b6d_add_slack_channel_and_min_severity.py`
(head):

- `ALTER TYPE alert_channel_type ADD VALUE 'slack'` (idempoten lewat pengecekan).
- `alert_channels.encrypted_slack_webhook_url` — `TEXT`, nullable.
- `alert_channels.min_severity` — `VARCHAR(20)`, default `info`, backfill baris lama.

```bash
# DB host (dipakai pytest)
cd backend && uv run --no-dev alembic upgrade head

# DB Docker
docker compose exec -T backend uv run --no-dev alembic upgrade head
```

> Catatan: PostgreSQL tidak mendukung penghapusan nilai enum saat downgrade.
> Kolom baru dihapus, nilai `slack` tetap ada di tipe enum.

## Backend

### Model & service

- `AlertChannelType` bertambah `slack`; `SEVERITY_ORDER`, `SEVERITY_RANK`, dan
  `severity_rank()` menjadi sumber tunggal peringkat severity.
- `alert_channel_repository.list_enabled_for_severity(db, severity)` memilih
  channel aktif dengan `severity_rank(min_severity) <= severity_rank(event)`.
- `alert_service` membangun payload per tipe:
  - Discord: embed dengan warna `critical` merah, `warning` amber, `resolved` hijau.
  - Slack: Block Kit + attachment color `#EF4444` / `#F59E0B` / `#22C55E`.
  - Telegram: HTML message, nilai di-escape.
- `send_test(channel, severity)` memakai `Test Notifikasi InfraForge` dan
  severity default `channel.min_severity`.

### API

| Method | Path | Permission | Keterangan |
|---|---|---|---|
| GET | `/alert-channels` | semua user login | Daftar channel, tanpa kredensial |
| POST | `/alert-channels` | `alert_channel:write` (admin) | Validasi konfigurasi per tipe |
| PATCH | `/alert-channels/{id}` | admin | Nama, threshold, status, kredensial opsional |
| DELETE | `/alert-channels/{id}` | admin | Hapus channel |
| POST | `/alert-channels/{id}/test` | admin | Kirim notifikasi uji; body severity opsional |

Contoh membuat channel Slack:

```json
{
  "name": "Tim Infra",
  "type": "slack",
  "slack_webhook_url": "https://hooks.slack.com/services/T000/B000/XXX",
  "min_severity": "warning",
  "enabled": true
}
```

Contoh test dengan override severity:

```bash
curl -X POST http://localhost:8000/alert-channels/3/test \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"severity": "critical"}'
```

Respons error pengiriman: `502` dengan detail
`Gagal mengirim notifikasi uji: <reason>` (dipotong 300 karakter). Audit
mencatat `CREATE_ALERT_CHANNEL`, `UPDATE_ALERT_CHANNEL`,
`DELETE_ALERT_CHANNEL`, dan `TEST_ALERT_CHANNEL`.

### Matriks routing

| Severity event | Channel `info` | Channel `warning` | Channel `critical` |
|---|:---:|:---:|:---:|
| `info` | ✅ | — | — |
| `warning` | ✅ | ✅ | — |
| `critical` | ✅ | ✅ | ✅ |
| tidak dikenal | ✅ | — | — |

Event `resolved` memakai severity alert aslinya, sehingga channel yang menerima
firing juga menerima resolved.

## Frontend

- **Settings → Notifikasi** (`components/alerts/alert-destinations.tsx`):
  - Ringkasan jumlah channel aktif dan per tipe.
  - Form tambah channel: Discord webhook, Telegram bot token + chat ID, Slack
    incoming webhook; pilihan threshold **Semua severity / Warning ke atas /
    Hanya critical**; switch aktif.
  - Aksi per channel: **Test notifikasi**, **Ubah** (dialog), **Hapus**
    (dialog konfirmasi), dan toggle aktif/nonaktif.
  - Feedback sukses/gagal ditampilkan di banner, termasuk alasan kegagalan dari
    backend.
  - Admin-only: developer/viewer melihat daftar tanpa tombol mutasi.
- **`/alerts` tab Channel**: ringkasan per tipe + tautan
  **Kelola di Pengaturan** ke `/settings?tab=notifications`.
- Test ID utama: `channel-summary`, `channel-add-button`, `channel-form`,
  `channel-name`, `channel-type`, `channel-discord-url`,
  `channel-telegram-token`, `channel-telegram-chat`, `channel-slack-url`,
  `channel-min-severity`, `channel-submit`, `channel-card`,
  `channel-severity-badge`, `channel-toggle`, `channel-test`, `channel-edit`,
  `channel-delete`, `channel-feedback`, `channel-empty`,
  `channel-edit-dialog`.

## Aturan Prometheus

Tiga aturan `warning` ditambahkan di samping aturan `critical` yang sudah ada:

| Rule | Kondisi | Severity |
|---|---|---|
| `HighHostCPUUsageWarning` | CPU host > 75% selama 5 menit | `warning` |
| `HighHostMemoryUsageWarning` | RAM host > 75% selama 5 menit | `warning` |
| `HighDiskUsageWarning` | Disk host > 80% selama 5 menit | `warning` |
| `HighHostCPUUsage` | CPU host > 90% selama 5 menit | `critical` |
| `HighHostMemoryUsage` | RAM host > 90% selama 5 menit | `critical` |
| `HighDiskUsage` | Disk host > 90% selama 5 menit | `critical` |
| `InfraContainerDown` | Container compose mati 2 menit | `critical` |
| `ContainerRestartLoop` | Restart > 2 kali dalam 15 menit | `critical` |
| `DockerDaemonUnavailable` | Docker daemon tidak terdeteksi | `critical` |
| `MonitoringTargetDown` | Target scrape Prometheus down | `critical` |

Ambang warning dan critical dapat menyala bersamaan saat pemakaian melewati
ambang critical; ini disengaja agar tim menerima eskalasi.

`docker-compose.yml` menambahkan
`extra_hosts: ["host.docker.internal:host-gateway"]` pada backend agar channel
uji di host (mis. mock webhook E2E) dapat dijangkau dari container.

## Pengujian

| Pemeriksaan | Hasil |
|---|---|
| `uv run --no-dev pytest -q` | **786 passed** (24 warning) |
| `uv run --no-dev ruff check app tests` | **0 temuan** |
| `uv run --no-dev mypy app` | **0 error** (107 source file) |
| Frontend `npm run lint` | 3 warning baseline, tanpa warning baru |
| Frontend `npm run build` | Sukses (`tsc -b && vite build`) |
| Alembic host & Docker | `9c4e1f7a2b6d (head)` |
| Prometheus live | 10 rules, 3 di antaranya `severity: warning` |
| `promtool check rules` | `SUCCESS: 10 rules found` |
| E2E alert destinations | **28/28** |
| E2E Settings (termasuk gating notifikasi) | **33/33** |
| E2E Audit Logs | **17/17** |
| E2E API Token | **19/19** |
| E2E Env Vars DoD | **22/22** |

Skenario E2E `alert-destinations-e2e.cjs` memakai mock webhook di
`127.0.0.1:9099` (bind `0.0.0.0`, diakses container lewat
`host.docker.internal:9099`) dan membuktikan:

1. Channel Discord (`critical`) dan Slack (`warning`) dapat dibuat dari UI.
2. Test notification sukses menerima payload nyata dengan warna sesuai severity.
3. Alert `warning` dari `POST /alerts/webhook` hanya dikirim ke Slack; alert
   `critical` dikirim ke Discord dan Slack.
4. Event `resolved` mengirim status resolved dengan warna hijau.
5. Mengubah threshold menjadi `critical` memfilter alert warning berikutnya.
6. Toggle nonaktif menghentikan pengiriman; developer tidak melihat aksi mutasi.
7. Hapus channel dari UI menghilangkan channel dari daftar.

Regresi M6 juga memverifikasi 9 halaman utama, tabel alert, live tail, dan
seluruh link sidebar. Suite regresi penuh 30/30 terakhir lulus pada verifikasi
Milestone 5 Fase 3; pada run ulang M6, login demo mengalami timeout frontend
transien setelah reboot mesin (API login tetap `200`) sehingga run tidak selesai.

## Keterbatasan

- Routing dilakukan backend, bukan `route` Alertmanager; Alertmanager tetap
  memakai satu receiver. Ini menjaga konfigurasi infra sederhana dan
  memungkinkan threshold diubah tanpa reload Alertmanager.
- Belum ada UI silence/mute jangka waktu tertentu; channel hanya bisa
  diaktifkan/nonaktifkan atau dihapus.
- `telegram_chat_id` disimpan plaintext (bukan rahasia seperti token/webhook);
  token dan URL webhook selalu terenkripsi.
- Nilai enum `slack` tidak bisa dihapus lewat downgrade migrasi.
