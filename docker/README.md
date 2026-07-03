# Docker configuration for RunMind
#
# The primary orchestration file lives at the repository root:
#   docker-compose.yml
#
# This directory holds supplementary Docker assets and documentation.

## Services

| Service  | Port | Description              |
|----------|------|--------------------------|
| backend  | 8000 | FastAPI API with hot reload |
| frontend | 3000 | Next.js dev server with hot reload |

## Network

All services join the `runmind-network` bridge network. The frontend
container reaches the backend at `http://backend:8000` for server-side
requests. Browser clients use `http://localhost:8000`.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

## Hot reload

- **Backend**: source is mounted at `/app`; Uvicorn runs with `--reload`.
- **Frontend**: source is mounted at `/app`; anonymous volumes preserve
  `node_modules` and `.next` across restarts.

## Health checks

The backend service exposes a health check at `/api/v1/health`. The frontend
waits for the backend to become healthy before starting.
