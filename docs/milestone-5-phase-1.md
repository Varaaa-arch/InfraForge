# Milestone 5 Fase 1 — Manajemen Infrastruktur & Lifecycle (Servers & Containers UI)

Dokumen ini adalah kontrak API + catatan verifikasi Fase 1 Milestone 5
InfraForge. Semua perubahan backend dan frontend pada fase ini mengikuti
kontrak di bawah.

## Tujuan Fase 1

Melengkapi sisi operasional dari metrik Milestone 4:

- **Halaman `/servers`** — tabel node/server beserta status koneksi Prometheus
  (`exporter_instance` aktif/tidak) + form tambah & edit server.
- **Halaman `/containers`** — daftar seluruh container aktif/berhenti dengan
  status health, image, port mapping, serta pemakaian CPU/RAM sekilas, lengkap
  dengan aksi Start / Stop / Restart dan Inspect.

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Sumber CPU/RAM container | Gauge Prometheus `infraforge_container_cpu_percent` / `infraforge_container_memory_bytes` (≤15 detik) |
| Form server | Lengkap: nama, host, port, username, metode auth, password/private key, `exporter_instance` (backend mewajibkan kredensial SSH saat create) |
| Aksi hapus | Hanya **server**. Hapus container tidak ada di Fase 1 (risiko merusak stack) |
| Dialog UI | Ditulis manual gaya shadcn-nova di atas paket `radix-ui` (tanpa dependensi baru) |

---

## Kontrak API

### `GET /containers`

Field baru bersifat **opsional** — field lama tidak berubah sehingga consumer
yang sudah ada tetap kompatibel.

```json
{
  "success": true,
  "data": [
    {
      "id": "d7b327296a7a",
      "name": "infraforge-frontend",
      "image": "infraforge-frontend",
      "status": "running",
      "created": "2026-11-13T13:44:02.123456789Z",
      "ports": [
        { "container_port": 80, "protocol": "tcp", "host_port": 5173, "host_ip": "0.0.0.0" }
      ],
      "health": "healthy",
      "compose_project": "infraforge",
      "compose_service": "frontend",
      "restart_count": 0,
      "cpu_percent": 1.42,
      "memory_usage_bytes": 52428800,
      "memory_limit_bytes": 1073741824,
      "memory_percent": 4.88
    },
    {
      "id": "622c15ab8cab",
      "name": "infraforge-backend",
      "image": "infraforge-backend",
      "status": "running",
      "created": "2026-11-13T13:44:01.987654321Z",
      "ports": [
        { "container_port": 8000, "protocol": "tcp", "host_port": 8000, "host_ip": "0.0.0.0" }
      ],
      "health": null,
      "compose_project": "infraforge",
      "compose_service": "backend",
      "restart_count": 0,
      "cpu_percent": 6.7,
      "memory_usage_bytes": 133000000,
      "memory_limit_bytes": 1073741824,
      "memory_percent": 12.39
    }
  ]
}
```

Aturan field:

| Field | Sumber | Catatan |
|---|---|---|
| `ports` | `NetworkSettings.Ports` | Satu entri per `(container_port, protocol, host_port)` unik. Port yang **di-expose tanpa publish** → `host_port: null`. Binding `0.0.0.0` dan `::` digabung menjadi satu entri |
| `health` | `State.Health.Status` | `null` bila container tidak punya healthcheck |
| `compose_project` / `compose_service` | label `com.docker.compose.project` / `.service` | `null` untuk container non-compose |
| `restart_count` | `RestartCount` | — |
| `cpu_percent` | gauge `infraforge_container_cpu_percent` (label `name`) | `null` bila Prometheus mati atau container tidak tercatat |
| `memory_usage_bytes` | gauge `infraforge_container_memory_bytes` | `null` bila tidak tersedia |
| `memory_limit_bytes` | gauge `infraforge_container_memory_limit_bytes` | baru; dipakai untuk menghitung persen RAM |
| `memory_percent` | `usage / limit * 100` | `null` bila limit atau usage tidak tersedia |

### `GET /servers` dan `GET /servers/{id}`

Menambah satu field baru, sisanya tetap sama.

```json
{
  "success": true,
  "data": [
    {
      "id": 9,
      "owner_id": 43,
      "name": "Demo Server 1",
      "host": "192.0.2.10",
      "port": 22,
      "username": "deploy",
      "exporter_instance": "host.docker.internal:9100",
      "auth_type": "password",
      "status": "active",
      "exporter_status": "up",
      "created_at": "2026-11-01T08:12:00Z",
      "updated_at": "2026-11-01T08:12:00Z"
    }
  ]
}
```

Nilai `exporter_status`:

| Nilai | Arti |
|---|---|
| `not_configured` | `exporter_instance` kosong |
| `up` | Target terdaftar di Prometheus dan `up == 1` |
| `down` | Target terdaftar di Prometheus dan `up == 0` |
| `unknown` | Exporter tidak terdaftar sebagai target, atau Prometheus tidak dapat dihubungi |

Field `exporter_status` bernilai `null` pada respons `POST /servers` dan
`PATCH /servers/{id}` (hanya diisi pada list & detail).

### Endpoint yang dipakai (sudah ada, tidak berubah)

| Method | Path | Pakai untuk |
|---|---|---|
| `POST` | `/servers` | Tambah server |
| `PATCH` | `/servers/{id}` | Edit server (partial) |
| `DELETE` | `/servers/{id}` | Hapus server |
| `POST` | `/servers/{id}/test` | Tes koneksi SSH (mengubah `status`) |
| `GET` | `/containers` | Daftar container (diperluas di atas) |
| `POST` | `/containers/{id}/start` | Start container |
| `POST` | `/containers/{id}/stop?timeout=10` | Stop container |
| `POST` | `/containers/{id}/restart?timeout=10` | Restart container |
| `GET` | `/containers/{id}/inspect` | Detail JSON container |

Format error tetap `{"success": false, "message": "...", "code": <status>}`.

---

## Work package

| Paket | Isi | Status |
|---|---|---|
| 1.1 | Kontrak API, tipe TS, API client, komponen `dialog` + `confirm-dialog` | ✅ selesai |
| 1.2 | Backend: daftar container kaya (ports, health, label compose, restart count) | ✅ selesai |
| 1.3 | Backend: usage container dari Prometheus + `exporter_status` server | ✅ selesai |
| 1.4 | Frontend: halaman `/servers` (tabel, form, tes SSH, hapus) | ✅ selesai |
| 1.5 | Frontend: halaman `/containers` (tabel, lifecycle, inspect) | ⏳ |
| 1.6 | Verifikasi menyeluruh, regresi Milestone 4, dokumentasi | ⏳ |

## Di luar scope Fase 1

Hapus/edit container · log container di UI (sudah ada di halaman Logs) · audit
trail · settings profil/token · integrasi webhook · Grafana/Traefik ·
self-service deploy (Fase 2) · platform operations (Fase 3).
