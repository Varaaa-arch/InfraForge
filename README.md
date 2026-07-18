# InfraForge

**Platform DevOps self-hosted open source** untuk membangun, mendeploy, memonitor, dan mengelola aplikasi semuanya dari satu dashboard terpusat.

> Bukan sekadar "dashboard Docker". InfraForge adalah **Internal Developer Platform (IDP)** sederhana yang menyatukan tool-tool DevOps yang biasanya berdiri sendiri (Docker, Traefik, Prometheus, Grafana, Loki, GitHub Actions) menjadi satu alur kerja yang mulus.

---

## Daftar Isi

- [Masalah yang Diselesaikan](#masalah-yang-diselesaikan)
- [Cara Kerja](#cara-kerja)
- [Arsitektur](#arsitektur)
- [Fitur Utama](#fitur-utama)
- [Tech Stack](#tech-stack)
- [Struktur Folder](#struktur-folder)
- [Getting Started](#getting-started)
- [Roadmap](#roadmap)
- [Kenapa Namanya InfraForge?](#kenapa-namanya-infraforge)
- [License](#license)

---

## Masalah yang Diselesaikan

Tanpa InfraForge, deploy aplikasi biasanya melewati banyak tool yang terpisah:

```
GitHub → GitHub Actions → Docker Build → Docker Push → SSH ke VPS
   → docker compose pull → docker compose up
   → buka Grafana → buka Prometheus → buka Loki
   → cek logs → cek container → cek SSL → backup database
```

Dengan InfraForge, alurnya jadi:

```
Push Code → GitHub Actions → InfraForge → Deploy
```

Sisanya routing, HTTPS, monitoring, logging, alerting, backup ditangani otomatis oleh platform.

---

## Cara Kerja

```mermaid
flowchart TD
    A[Developer push code] --> B[GitHub Repository]
    B --> C["GitHub Actions<br/>lint → test → build image"]
    C --> D[Push image ke GHCR]
    D --> E[InfraForge mendeteksi image terbaru]
    E --> F["docker compose up<br/>+ health check"]
    F --> G[Traefik: routing & HTTPS otomatis]
    F --> H[Prometheus: scrape metrics]
    F --> I[Logs dikirim ke Loki]
    H --> J[Grafana Dashboard]
    I --> J
    H --> K[Alertmanager]
    K --> L["Notifikasi ke Discord / Telegram"]
```

1. **Push** -> developer push code ke GitHub.
2. **CI** -> GitHub Actions menjalankan lint, test, build image, lalu push ke GHCR.
3. **Deploy** -> InfraForge menarik image terbaru dan menjalankan `docker compose up` beserta health check.
4. **Routing** -> Traefik otomatis membuat routing dan HTTPS untuk domain aplikasi.
5. **Observability** -> Prometheus mengambil metric, Loki mengumpulkan log, semuanya tampil di Grafana.
6. **Alerting** -> Alertmanager mengirim notifikasi ke Discord/Telegram saat CPU tinggi, RAM penuh, atau container mati.

---

## Arsitektur

```mermaid
flowchart TD
    Dashboard[InfraForge Dashboard]
    Dashboard --> Backend["Backend (FastAPI)"]
    Dashboard --> Frontend["Frontend (React)"]
    Dashboard --> CLI["CLI (Typer)"]

    Backend --> Docker
    Backend --> PostgreSQL
    Backend --> Redis
    Backend --> MinIO
    Backend --> Traefik
    Backend --> Prometheus
    Backend --> Grafana
    Backend --> Loki
    Backend --> Alertmanager
    Backend --> GHA[GitHub Actions]
```

---

## Fitur Utama

| Kategori | Detail |
|---|---|
| **Deployment** | Deploy aplikasi hanya dengan beberapa klik |
| **Container Management** | Start, stop, restart, delete, view logs |
| **Monitoring** | CPU, RAM, Disk, Docker, Network, Uptime |
| **Logging** | Lihat log seluruh container dari satu tempat |
| **Project Management** | Satu server bisa kelola banyak project sekaligus |
| **Authentication** | JWT-based authentication |
| **Backup** | Backup database & file ke MinIO |
| **Dashboard** | Ringkasan container, resource usage, deployment history, alerts |

---

## Tech Stack

**Language**

![Python](https://img.shields.io/badge/Python_3.13-3776AB?style=flat&logo=python&logoColor=white)
![Bash](https://img.shields.io/badge/Bash-4EAA25?style=flat&logo=gnubash&logoColor=white)

**Backend**

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat)
![Alembic](https://img.shields.io/badge/Alembic-4B8BBE?style=flat)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=flat&logo=pydantic&logoColor=white)
![Uvicorn](https://img.shields.io/badge/Uvicorn-2E2E2E?style=flat)

**Frontend**

![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react&logoColor=61DAFB)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat&logo=tailwindcss&logoColor=white)
![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-000000?style=flat&logo=shadcnui&logoColor=white)
![TanStack Query](https://img.shields.io/badge/TanStack_Query-FF4154?style=flat&logo=reactquery&logoColor=white)
![React Router](https://img.shields.io/badge/React_Router-CA4245?style=flat&logo=reactrouter&logoColor=white)

**Database**

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)

**Cache**

![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white)

**Reverse Proxy**

![Traefik](https://img.shields.io/badge/Traefik-24A1C1?style=flat&logo=traefikproxy&logoColor=white)

**SSL**

![Let's Encrypt](https://img.shields.io/badge/Let's_Encrypt-003A70?style=flat&logo=letsencrypt&logoColor=white)

**Container**

![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat&logo=docker&logoColor=white)

**Container Registry**

![GHCR](https://img.shields.io/badge/GHCR-181717?style=flat&logo=github&logoColor=white)

**CI/CD**

![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat&logo=githubactions&logoColor=white)

**Monitoring**

![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat&logo=grafana&logoColor=white)
![Node Exporter](https://img.shields.io/badge/Node_Exporter-E6522C?style=flat&logo=prometheus&logoColor=white)
![cAdvisor](https://img.shields.io/badge/cAdvisor-2496ED?style=flat&logo=docker&logoColor=white)

**Logging**

![Loki](https://img.shields.io/badge/Loki-F5A623?style=flat&logo=grafana&logoColor=white)
![Promtail](https://img.shields.io/badge/Promtail-F5A623?style=flat&logo=grafana&logoColor=white)

**Alerting**

![Alertmanager](https://img.shields.io/badge/Alertmanager-E6522C?style=flat&logo=prometheus&logoColor=white)

**Object Storage**

![MinIO](https://img.shields.io/badge/MinIO-C72E49?style=flat&logo=minio&logoColor=white)

**Documentation**

![MkDocs Material](https://img.shields.io/badge/MkDocs_Material-526CFE?style=flat&logo=materialformkdocs&logoColor=white)

**Testing**

![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=flat&logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?style=flat&logo=ruff&logoColor=black)
![mypy](https://img.shields.io/badge/mypy-2A6DB2?style=flat)

**API Testing**

![Bruno](https://img.shields.io/badge/Bruno-2B615F?style=flat)

**CLI**

![Typer](https://img.shields.io/badge/Typer-000000?style=flat&logo=python&logoColor=white)

**DNS**

![Cloudflare](https://img.shields.io/badge/Cloudflare-F38020?style=flat&logo=cloudflare&logoColor=white)

---

## Struktur Folder

```
InfraForge/
├── backend/          # FastAPI app (api, core, models, services, dst)
├── frontend/         # React app
├── infrastructure/   # Config Traefik, Postgres, Redis, MinIO, Prometheus, Grafana, Loki, dst
├── cli/              # CLI berbasis Typer
├── docs/             # Dokumentasi tambahan
├── .github/workflows # CI/CD pipelines
└── docker-compose.yml
```

---

## Getting Started

```bash
git clone https://github.com/Varaaa-arch/InfraForge.git
cd InfraForge
cp .env.example .env
docker compose up -d
```

> Setup lengkap masih dalam pengembangan, instruksi detail akan ditambahkan seiring progress.

---

## Kenapa Namanya InfraForge?

- **Infra** = Infrastructure
- **Forge** = menempa, membangun sesuatu yang kuat

> *"Tempat untuk membangun, mengelola, dan mengoperasikan infrastruktur aplikasi."*

Nama ini sengaja dibuat fleksibel saat project berkembang ke arah Kubernetes, GitOps, atau multi-cloud, nama **InfraForge** tetap relevan.

---

## License

Lisensi project ini akan ditentukan segera lihat file `LICENSE` untuk detail terbaru.