# RunMind

The AI-powered platform for runners.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.14 |
| Database | Supabase (PostgreSQL) |
| Architecture | Clean Architecture, DDD, SOLID |
| DevOps | Docker, Docker Compose |

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| OpenAPI docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |

## Project structure

```
runmind/
├── frontend/           Next.js application
├── backend/            FastAPI application (Clean Architecture)
├── supabase/           Database migrations and Supabase config
├── docker/             Docker documentation
├── docs/               Architecture and development guides
├── docker-compose.yml  Local development stack
└── .env.example        Environment variable template
```

## Documentation

- [Architecture](docs/architecture.md)
- [Development guide](docs/development.md)
- [Environment variables](docs/environment.md)

## Local development (without Docker)

**Backend**

```bash
cd backend
cp .env.example .env
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## License

See [LICENSE](LICENSE).
