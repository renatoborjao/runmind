# Development Guide

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2
- [Node.js](https://nodejs.org/) 22+ (for local frontend development)
- [Python](https://www.python.org/) 3.14+ (for local backend development)
- [Supabase CLI](https://supabase.com/docs/guides/cli) (optional, for local Supabase)

## Option A — Docker (recommended)

1. Copy environment variables:

   ```bash
   cp .env.example .env
   ```

2. Start all services with hot reload:

   ```bash
   docker compose up --build
   ```

3. Open the app:

   | Service | URL |
   |---------|-----|
   | Frontend | http://localhost:3000 |
   | Backend API | http://localhost:8000 |
   | OpenAPI docs | http://localhost:8000/docs |
   | Health check | http://localhost:8000/api/v1/health |

4. Stop services:

   ```bash
   docker compose down
   ```

## Option B — Local development

### Backend

```bash
cd backend
cp .env.example .env
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run tests:

```bash
pytest
```

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Set `API_URL=http://localhost:8000` in `frontend/.env` when running locally (not in Docker).

### Supabase (optional)

```bash
cd supabase
supabase start
supabase db reset   # applies migrations and seed
```

Update `.env` with the local Supabase URL and keys printed by `supabase start`.

## Project structure

```
runmind/
├── frontend/           Next.js 15 application
├── backend/            FastAPI application
├── supabase/           Database migrations and config
├── docker/             Docker documentation
├── docs/               Project documentation
├── docker-compose.yml  Local development stack
└── .env.example        Environment template
```

## Code quality

Backend linting with Ruff:

```bash
cd backend
ruff check .
```

Frontend linting:

```bash
cd frontend
npm run lint
```
