# Contributing to InfraForge

Makasih udah tertarik buat kontribusi ke InfraForge! Dokumen ini isinya panduan singkat biar proses kontribusi lu lancar.

---

## Daftar Isi

- [Cara Berkontribusi](#cara-berkontribusi)
- [Melaporkan Bug](#melaporkan-bug)
- [Mengusulkan Fitur](#mengusulkan-fitur)
- [Setup Development](#setup-development)
- [Alur Kerja Git](#alur-kerja-git)
- [Standar Commit](#standar-commit)
- [Coding Style](#coding-style)
- [Testing](#testing)
- [Pull Request](#pull-request)
- [Lisensi](#lisensi)

---

## Cara Berkontribusi

Ada banyak cara buat bantu project ini, gak harus nulis kode:

- Laporin bug yang lu temuin
- Usulin fitur baru
- Perbaiki atau tambahin dokumentasi
- Review Pull Request orang lain
- Bantu jawab pertanyaan di Issues/Discussions

---

## Melaporkan Bug

Sebelum bikin issue baru, cek dulu di tab **Issues** — siapa tau bug-nya udah pernah dilaporin.

Kalau belum ada, bikin issue baru pake template **Bug Report** dan isi selengkap mungkin (langkah reproduksi, environment, log error).

---

## Mengusulkan Fitur

Buat issue baru pake template **Feature Request**. Jelasin masalah yang mau diselesaikan, bukan cuma solusinya — biar diskusinya lebih terbuka.

---

## Setup Development

### Prasyarat

- Python 3.13+
- Node.js (buat frontend)
- Docker & Docker Compose
- Git

### Langkah

```bash
# Clone repo
git clone https://github.com/Varaaa-arch/InfraForge.git
cd InfraForge

# Copy env
cp .env.example .env

# Jalankan stack
docker compose up -d
```

**Backend (FastAPI):**

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements/dev.txt
uvicorn app.main:app --reload
```

**Frontend (React + Vite):**

```bash
cd frontend
npm install
npm run dev
```

---

## Alur Kerja Git

1. Fork repo ini
2. Bikin branch baru dari `main`:
   ```bash
   git checkout -b feat/nama-fitur
   ```
3. Commit perubahan lu (lihat [Standar Commit](#standar-commit))
4. Push ke fork lu:
   ```bash
   git push origin feat/nama-fitur
   ```
5. Buka Pull Request ke branch `main`

### Konvensi Nama Branch

| Prefix | Kegunaan |
|---|---|
| `feat/` | Fitur baru |
| `fix/` | Perbaikan bug |
| `docs/` | Perubahan dokumentasi |
| `refactor/` | Refactor tanpa ubah behavior |
| `chore/` | Maintenance, config, dependency |

---

## Standar Commit

Project ini pake gaya [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <deskripsi singkat>
```

Contoh:

```
feat: tambah endpoint deploy container
fix: perbaiki bug health check gagal timeout
docs: update instruksi setup di README
chore: bump versi dependency FastAPI
```

Type yang umum dipake: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

---

## Coding Style

**Backend (Python):**

- Format & lint pake `ruff`
- Type checking pake `mypy`
- Ikutin struktur folder yang udah ada (`api/`, `core/`, `services/`, `schemas/`, dst)

```bash
ruff check .
ruff format .
mypy .
```

**Frontend (TypeScript/React):**

- Ikutin konvensi komponen yang udah ada di `src/components/`
- Pake Tailwind CSS untuk styling, hindari inline style
- State server pake TanStack Query, jangan simpan di local state kalau data-nya dari API

---

## Testing

Semua fitur baru atau bug fix sebaiknya disertai test.

```bash
cd backend
pytest
```

Pastiin semua test lulus sebelum buka Pull Request.

---

## Pull Request

Sebelum submit PR, pastiin:

- [ ] Branch lu up-to-date sama `main`
- [ ] Semua test lulus
- [ ] Lint (`ruff`) dan type check (`mypy`) bersih
- [ ] Deskripsi PR jelasin **apa** yang berubah dan **kenapa**
- [ ] Kalau nutup issue tertentu, tulis `Closes #<nomor-issue>` di deskripsi PR

PR bakal direview sebelum di-merge. Jangan ragu buat nanya kalau ada review yang kurang jelas.

---

## Lisensi

Dengan berkontribusi ke InfraForge, lu setuju kalau kontribusi lu dilisensikan di bawah [Apache License 2.0](LICENSE) yang sama dengan project ini.