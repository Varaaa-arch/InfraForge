# InfraForge Frontend

Dashboard web InfraForge berbasis React + TypeScript.

## Stack

- Vite + React 19 + TypeScript
- Tailwind CSS v4 + shadcn/ui
- TanStack Query
- React Router

## Menjalankan

```bash
npm install
npm run dev
```

Buka http://localhost:5173. Backend diasumsikan berjalan di
`http://localhost:8000` (bisa diubah lewat `VITE_API_URL`).

## Docker

Dari root repo:

```bash
docker compose up -d --build frontend
```

Dashboard tersedia di http://localhost:5173. Image produksi memakai nginx:
hasil build statis disajikan langsung, sedangkan request `/api` (REST dan
WebSocket) di-proxy ke service `backend` agar same-origin. Saat build Docker,
`VITE_API_URL` diisi `/api`; untuk dev lokal nilainya default
`http://localhost:8000`.

## Perintah

```bash
npm run dev      # development server
npm run build    # type-check + build produksi
npm run lint     # oxlint
npm run preview  # preview hasil build
```
