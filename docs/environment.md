# Environment Variables

Copy `.env.example` to `.env` at the repository root before starting services.

## Backend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_NAME` | No | `runmind-api` | Service identifier returned by health check |
| `APP_VERSION` | No | `0.1.0` | Application version |
| `APP_ENV` | No | `development` | Environment name (`development`, `staging`, `production`) |
| `DEBUG` | No | `false` | Enable debug mode |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8000` | Server port |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed CORS origins |
| `SUPABASE_URL` | Yes* | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes* | — | Supabase anonymous/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes* | — | Supabase service role key (backend only, never expose to frontend) |

\* Required once Supabase integration is used. The foundation scaffold starts without them.

## Frontend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Public API URL for browser requests |
| `API_URL` | No | `http://localhost:8000` | Internal API URL for server-side requests (set to `http://backend:8000` in Docker) |
| `NEXT_PUBLIC_APP_NAME` | No | `RunMind` | Application display name |

## Docker Compose overrides

`docker-compose.yml` sets `API_URL=http://backend:8000` for the frontend container so server-side rendering can reach the backend over the Docker network.

## Security notes

- Never commit `.env` files — they are listed in `.gitignore`.
- Never expose `SUPABASE_SERVICE_ROLE_KEY` to the frontend or client-side code.
- Use `SUPABASE_ANON_KEY` only in the frontend when Supabase client-side auth is added.
