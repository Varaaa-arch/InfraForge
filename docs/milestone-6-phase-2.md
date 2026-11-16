# Milestone 6 Fase 2 — Auto-Healing & Container Resource Management

Fase ini membuat container yang dikelola lewat Docker Compose dapat diberi
batas CPU/memory dari dashboard, lalu dipantau kesehatannya. Container dengan
auto-healing aktif akan di-restart otomatis ketika healthcheck gagal
berturut-turut, dan setiap insiden tercatat di Audit Logs.

## Ringkasan paket

| Paket | Isi | Commit |
|---|---|---|
| 6.1 | Backend: model policy, migrasi, API limit CPU/memory/restart, reapply saat lifecycle | `5b8ce29` |
| 6.2 | Backend: worker health polling, auto-restart, audit insiden, endpoint daftar & insiden | `2d43464` |
| 6.3 | Frontend: dialog resource per container + tab Auto-Healing | `f09dacb` |
| 6.4 | Verifikasi menyeluruh + dokumentasi | commit dokumen ini |

## Keputusan desain

| Topik | Keputusan |
|---|---|
| Penerapan limit | `POST /containers/{id}/update` langsung ke Docker **dan** disimpan di DB |
| Reapply | Policy diterapkan ulang otomatis saat container start/restart dan setelah `docker compose up` |
| Kunci policy | Nama container (ID berubah saat recreate oleh compose) |
| Auto-healing | Opt-in per container; default nonaktif untuk container baru |
| Pemicu restart | `unhealthy_streak >= unhealthy_threshold`; dibatasi `max_restarts` per window dan `restart_cooldown_seconds` |
| Insiden | Audit log system (`method=SYSTEM`, `username=system`), bukan tabel baru |
| Lokasi UI | Dialog per baris di halaman **Containers** + tab **Auto-Healing** |
| Worker | Asyncio task di lifespan backend, bukan ARQ worker |
| Reset limit | Tidak didukung Docker Engine API live (lihat Keterbatasan) |

## Migrasi

`backend/alembic/versions/b7c2d4e9f1a3_add_container_policies.py` (head,
`down_revision = 9c4e1f7a2b6d`):

- Tabel `container_policies` — satu baris per nama container.
- Unique index `container_name`; index `auto_heal_enabled`.
- Kolom limit: `cpu_limit_cores`, `cpu_quota`, `cpu_period`,
  `memory_limit_bytes`, `restart_policy`.
- Kolom auto-healing: `auto_heal_enabled`, `unhealthy_threshold`,
  `max_restarts`, `restart_cooldown_seconds`.
- Kolom runtime: `unhealthy_streak`, `last_health_status`, `last_restart_at`,
  `restart_count_window`, `window_started_at`, `applied_at`.
- Metadata: `container_id`, `compose_project`, `compose_service`, timestamps.

```bash
# DB host (dipakai pytest)
cd backend && uv run --no-dev alembic upgrade head

# DB Docker
docker compose exec -T backend uv run --no-dev alembic upgrade head
```

## Backend

### Model & repository

- `app/models/container_policy.py` — `ContainerPolicy`.
- `app/repositories/container_policy_repository.py` — lookup per nama,
  daftar semua, daftar per project, daftar policy auto-healing aktif.
- `container_name` menjadi kunci karena `docker compose up` dapat membuat
  ulang container dengan ID baru sementara namanya tetap.

### Penerapan limit

`container_policy_service` membangun body Engine API dan memanggil
`client.api._post_json` langsung, karena `container.update()` docker-py:

- tidak mendukung `NanoCpus`, dan
- mengabaikan nilai `0` (pengecekan truthy), sehingga tidak bisa mengirim
  payload lengkap.

Body yang dikirim selalu memuat `CpuPeriod`, `CpuQuota`, `Memory`, dan
`RestartPolicy`. Limit CPU dari UI dikonversi ke quota:
`cpu_quota = cores × cpu_period` (periode default `100000`).

Hook reapply bersifat best-effort agar kegagalan Docker tidak menggagalkan
lifecycle container:

- `container_service.start_container` dan `restart_container` →
  `container_policy_service.reapply_for_container(name)`.
- `deployment_service` setelah `_run_compose` →
  `container_policy_service.reapply_all()` dan menulis jumlah policy yang
  berhasil diterapkan ke log deployment.

### API

| Method | Path | Izin | Keterangan |
|---|---|---|---|
| `GET` | `/containers/{id}/policy` | login | Detail container, policy tersimpan, dan limit efektif |
| `PUT` | `/containers/{id}/policy` | `container:lifecycle` | Upsert policy; `apply_now=true` langsung diterapkan |
| `DELETE` | `/containers/{id}/policy` | `container:lifecycle` | Hapus policy tersimpan |
| `GET` | `/container-policies` | login | Daftar policy + status worker |
| `GET` | `/container-policies/incidents` | login | Insiden dari audit log (`container_name`, `limit`) |

Payload `PUT` utama: `cpu_limit_cores`, `cpu_quota`/`cpu_period`,
`memory_limit_mib` (0 = tanpa limit), `restart_policy`, `auto_heal_enabled`,
`unhealthy_threshold`, `max_restarts`, `restart_cooldown_seconds`,
`apply_now`. Validasi 422 untuk nilai tidak masuk akal; kegagalan apply
setelah policy tersimpan menghasilkan 502 dengan pesan yang jelas.

### Worker auto-healing

`app/services/auto_heal_service.py` dijalankan dari lifespan `app/main.py`.

- `decide_action()` adalah fungsi murni: `noop`, `record_unhealthy`,
  `restart`, atau `record_recovered`.
- Cooldown dan batas restart per window dicek sebelum memutuskan restart.
- Window restart di-reset otomatis setelah `AUTO_HEAL_WINDOW_MINUTES`.
- Pemanggilan Docker dijalankan lewat `asyncio.to_thread` agar event loop
  FastAPI tidak terblokir.
- Container tanpa healthcheck atau berstatus `starting` tidak dianggap
  unhealthy.
- Container yang sudah hilang (`NotFound`) dilewati tanpa error.
- Worker berhenti rapi saat shutdown (stop event + timeout).

Audit system event yang ditulis:

| Action | Kapan | Detail penting |
|---|---|---|
| `CONTAINER_UNHEALTHY` | Cek unhealthy di bawah ambang | `streak`, `threshold`, `health` |
| `CONTAINER_AUTO_RESTART` | Ambang tercapai dan budget restart tersedia | `result`, `restart_count_window`, `max_restarts`, `reason` |
| `CONTAINER_RECOVERED` | Kembali healthy setelah streak/restart | `previous_health`, `health` |
| `CONTAINER_POLICY_UPDATE` | `PUT` policy lewat middleware HTTP | path & resource container |
| `CONTAINER_POLICY_DELETE` | `DELETE` policy lewat middleware HTTP | path & resource container |

### Konfigurasi

| Env | Default config | docker-compose | Arti |
|---|---|---|---|
| `AUTO_HEAL_ENABLED` | `false` | `true` | Worker berjalan saat startup |
| `HEALTH_POLL_INTERVAL_SECONDS` | `30` | `30` | Interval polling (minimum 5 detik) |
| `HEALTH_UNHEALTHY_THRESHOLD` | `3` | `3` | Ambang default policy baru |
| `AUTO_HEAL_MAX_RESTARTS` | `3` | `3` | Batas default restart per window |
| `AUTO_HEAL_COOLDOWN_SECONDS` | `300` | `300` | Jeda default antar-restart |
| `AUTO_HEAL_WINDOW_MINUTES` | `60` | `60` | Panjang window penghitungan restart |

Default config `false` menjaga test dan dev tanpa Docker tetap tenang;
docker-compose menyalakan worker untuk deployment.

## Frontend

- **Halaman Containers** — tombol baru "Atur resource" per baris (ikon
  settings) membuka dialog limit CPU/memory, restart policy, dan auto-healing.
  Nilai efektif dari Docker ditampilkan di bagian atas dialog.
- **Tab Auto-Healing** — status worker (aktif/interval/poll terakhir/siklus
  terakhir), tabel policy, dan daftar 25 insiden terakhir.
- Aksi mutasi hanya tampil untuk peran dengan izin `canDeploy`
  (developer/admin); viewer tetap bisa melihat daftar dan insiden.
- Setelah simpan/hapus, query container, policy, dan insiden di-invalidate
  agar UI langsung konsisten.

## Pengujian

| Pemeriksaan | Hasil |
|---|---|
| `uv run --no-dev pytest -q` | **826 passed** (24 warning) |
| `uv run --no-dev ruff check app tests` | **0 temuan** |
| `uv run --no-dev mypy app` | **0 error** (113 source file) |
| Frontend `npm run lint` | 3 warning baseline, tanpa warning baru |
| Frontend `npm run build` | Sukses (`tsc -b && vite build`) |
| Alembic host & Docker | `b7c2d4e9f1a3 (head)` |
| E2E auto-healing & resource limit | **38/38** |

Test backend baru:

- `tests/test_container_policy.py` — konversi limit, payload Engine API,
  upsert/delete, reapply, gating permission, endpoint policy.
- `tests/test_auto_heal.py` — keputusan murni (ambang, cooldown, window,
  recovery), poller dengan Docker mock, audit system, endpoint daftar dan
  insiden.

Skenario E2E `/tmp/opencode/ui-test/auto-heal-e2e.cjs` (Chrome headless via
CDP, worker dijalankan dengan interval 5 detik) membuktikan:

1. Container uji dengan healthcheck gagal tampil di halaman Containers.
2. Dialog "Atur resource" menyimpan CPU 0.5 core, memory 64 MiB, auto-healing
   dengan ambang 1, maksimal 1 restart, dan cooldown 0.
3. Docker benar-benar menerima limit: `HostConfig.Memory=67108864`,
   `CpuQuota=50000`, `CpuPeriod=100000`.
4. Worker mencatat `CONTAINER_AUTO_RESTART` baru dan `State.StartedAt`
   container berubah (bukti restart nyata).
5. `CONTAINER_POLICY_UPDATE` muncul di Audit Logs.
6. Tab Auto-Healing menampilkan worker aktif, policy, dan insiden terbaru.
7. Viewer tidak melihat tombol "Atur resource"/"Atur policy"; developer dan
   admin melihatnya.
8. Cleanup menghapus policy dan menonaktifkan akun viewer uji.

Setelah E2E, backend dikembalikan ke interval polling default 30 detik dan
container uji dihapus.

## Keterbatasan

- Docker Engine API menganggap `Memory: 0` dan `CpuQuota: 0` pada update
  sebagai "tanpa perubahan". Limit yang sudah aktif **tidak bisa dihapus**
  lewat `docker update`; limit baru hilang saat container dibuat ulang
  (mis. `docker compose up --force-recreate`). Karena itu tombol hapus hanya
  menghapus policy tersimpan, bukan limit aktif.
- Worker berjalan di proses backend; bila backend mati, tidak ada polling.
  Belum ada leader election untuk multi-replica backend.
- Auto-healing membutuhkan healthcheck di container. Container tanpa
  healthcheck hanya mendapat limit resource.
- Worker tidak membuat ulang container, hanya restart; perubahan image atau
  konfigurasi compose tetap lewat deployment.
- Insiden saat ini hanya masuk Audit Logs dan tab Auto-Healing, belum dikirim
  ke channel notifikasi.
- `restart_policy` Docker tidak diubah ulang saat container start/restart;
  nilai reapply berlaku untuk limit resource.
