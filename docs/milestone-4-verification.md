# Milestone 4 — Verifikasi Observability

Dokumen ini mencatat bukti penyelesaian Definition of Done (DoD) Milestone 4
InfraForge. Verifikasi dilakukan pada 13 November 2026 menggunakan stack Docker
Compose penuh (`docker compose up -d`) dan data demo dari `scripts/seed_demo.py`.

## Ringkasan DoD

| # | DoD | Status |
|---|---|---|
| 1 | Prometheus & cAdvisor melakukan scraping metrik server dan container | Terpenuhi |
| 2 | Loki & Promtail mengumpulkan dan menampilkan log secara real-time | Terpenuhi |
| 3 | Alert otomatis terkirim ke Telegram/Discord saat resource melewati batas | Terpenuhi (bukti end-to-end) |
| 4 | Halaman Monitoring & Logs di dashboard dapat diakses dengan lancar | Terpenuhi |

---

## 1. Scraping metrik (Prometheus & cAdvisor)

Target scrape Prometheus (`GET /api/v1/targets`):

| Job | Target | Health |
|---|---|---|
| `prometheus` | `prometheus:9090` | up |
| `node-exporter` | `node-exporter:9100` | up |
| `cadvisor` | `cadvisor:8080` | up |
| `alertmanager` | `alertmanager:9093` | up |
| `backend` | `backend:8000` | up |

- cAdvisor mengekspos metrik container mentah (`container_cpu_usage_seconds_total`,
  `container_memory_working_set_bytes`, dll.).
- Exporter backend (`GET /metrics`) menyediakan metrik container **bernama** yang
  dipakai UI dan rules:

  | Metrik | Label |
  |---|---|
  | `infraforge_container_cpu_percent` | `name`, `service`, `compose_project`, `image` |
  | `infraforge_container_memory_bytes` | idem |
  | `infraforge_container_up` | idem + `state` |
  | `infraforge_container_restart_count` | idem |

  Stats container dikumpulkan paralel (`ThreadPoolExecutor`) agar scrape tetap
  di bawah timeout Prometheus.

- Endpoint tren container: `GET /containers/usage/top?range=1h&limit=5`
  mengembalikan top container berdasarkan CPU (`topk` + filter container
  berjalan), lengkap dengan pemakaian RAM dan `cpu_points` historis dari
  Prometheus. Contoh hasil verifikasi: 5 container, CPU 3–7%, RAM 7–133 MB,
  `step_seconds=15`.

UI: halaman **Overview** menampilkan 6 kartu statistik + health server;
halaman **Monitoring** menampilkan 4 grafik node-exporter (CPU, RAM, disk,
network) dan panel **Top container** (bar CPU/RAM + sparkline CPU 5 menit
terakhir, auto-refresh 30 detik).

---

## 2. Logging real-time (Loki & Promtail)

- `GET /ready` Loki → `ready`; index log mencakup container Docker yang
  berjalan (contoh: `infraforge-backend`, `infraforge-frontend`,
  `infraforge-prometheus`, dll.).
- API backend:
  - `GET /logs?container=...&limit=...` — query riwayat log dari Loki.
  - `GET /logs/containers` — daftar container yang punya log.
  - `WS /ws/logs` — streaming log (live tail) via WebSocket.
- Promtail mempublikasikan port `9080` untuk operasional
  (`/targets`, `/ready`, `/metrics` merespons HTTP 200).
- Uji E2E live tail: mengaktifkan toggle **Live**, memicu request
  `GET /health?e2e_live_<timestamp>`, lalu baris log backend muncul lewat
  WebSocket **tanpa reload halaman** (5/5 check lulus).

---

## 3. Alert otomatis ke Discord

Pipeline: **Prometheus rules → Alertmanager → backend webhook → PostgreSQL →
channel Discord/Telegram**.

Konfigurasi:

- 7 rules bawaan di `infrastructure/prometheus/rules/alerts.yml`.
- Alertmanager mengirim ke `http://backend:8000/alerts/webhook` dengan header
  `X-InfraForge-Token` (`ALERT_WEBHOOK_SECRET`, default `dev-alert-token`).
- Backend menyimpan `alert_events` dan mengirim notifikasi ke channel aktif
  (`InfraDC`, Discord) secara asynchronous dengan `httpx`.

Bukti end-to-end memakai **canary rule sementara** (`InfraForgeCanaryTest`,
`expr: vector(1)`, `for: 0m`, severity `warning`, component `monitoring`) yang
kemudian dihapus kembali:

| Waktu (UTC) | Kejadian |
|---|---|
| 14:09:16 | Alert canary mulai firing di Prometheus/Alertmanager |
| 14:09:26 | `POST /alerts/webhook` → `202`, log: `1 alert diterima, 1 firing baru` |
| 14:09:26 | `alert_events` mencatat event `firing` (id 79) |
| 14:09:26 | Log dispatch: `Alert 'InfraForgeCanaryTest' (firing) dikirim ke channel InfraDC` |
| 14:09:xx | Baris alert canary tampil di halaman **Alerts** UI |
| 14:13:16 | Alert resolved; event diperbarui menjadi `resolved` (`ends_at` terisi) |

Setelah bukti tercatat, file canary dihapus dan event uji dibersihkan dari
database sehingga data demo kembali ke 24 event (8 firing, 16 resolved).

---

## 4. Dashboard Monitoring & Logs

Uji E2E Playwright (Chrome headless, login `demo`):

| Skenario | Hasil |
|---|---|
| Overview: 6 kartu (2/2/8/1/4/16), health 2 server, badge metrik aktif | 24/24 check lulus |
| Monitoring: 4 grafik Recharts, dropdown server, filter range, muat ulang | lulus |
| Alerts: tabel 6 kolom, firing & resolved | lulus |
| Logs: halaman dan viewer tetap berfungsi | lulus |
| Live tail WebSocket | 5/5 check lulus |
| Panel Top container: 5 baris, bar CPU/RAM, sparkline, ganti range, muat ulang | 9/9 check lulus |

Tidak ada `pageerror` pada semua skenario.

---

## Cara Mereproduksi

```bash
docker compose up -d --build

# Target scrape (harus 5 up)
curl -s http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[].labels.job'

# Metrik container bernama dari exporter backend
curl -s http://127.0.0.1:8000/metrics | grep '^infraforge_container_'

# Endpoint tren container (butuh token login)
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -d 'username=demo&password=demo1234' | jq -r '.data.access_token')
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/containers/usage/top?range=1h&limit=5' | jq

# Kesiapan Loki & Promtail
curl -s http://127.0.0.1:3100/ready
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9080/ready

# Riwayat alert
curl -s http://127.0.0.1:9093/api/v2/alerts
```

Hasil pengujian otomatis pada verifikasi ini:

- `pytest`: **639 passed**, 5 failure pre-existing pada `tests/test_cli.py`
  (tidak terkait Milestone 4).
- `ruff check app tests`: 10 temuan baseline.
- `mypy app`: 3 temuan baseline pada `app/worker.py`.
- `npm run lint`: 3 warning baseline (fast-refresh & efek React).
- `npm run build`: sukses.
