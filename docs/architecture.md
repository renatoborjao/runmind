# Architecture

RunMind follows **Clean Architecture** with **Domain-Driven Design (DDD)** principles and **SOLID** design guidelines.

## High-level overview

```
┌─────────────────────────────────────────────────────────┐
│                     Presentation                        │
│              (FastAPI routes, Pydantic schemas)         │
├─────────────────────────────────────────────────────────┤
│                     Application                         │
│                  (Use cases, DTOs)                      │
├─────────────────────────────────────────────────────────┤
│                       Domain                            │
│        (Entities, value objects, repository ports)      │
├─────────────────────────────────────────────────────────┤
│                    Infrastructure                       │
│           (Supabase, external services, adapters)       │
└─────────────────────────────────────────────────────────┘
```

Dependency rule: inner layers never depend on outer layers. The domain has no knowledge of FastAPI, Supabase, or HTTP.

## Backend layers

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Domain** | `backend/app/domain/` | Core business concepts — entities, value objects, repository interfaces |
| **Application** | `backend/app/application/` | Use cases that orchestrate domain logic; input/output DTOs |
| **Infrastructure** | `backend/app/infrastructure/` | Concrete implementations — Supabase client, external APIs |
| **Presentation** | `backend/app/presentation/` | HTTP API routes, request/response schemas |
| **Core** | `backend/app/core/` | Cross-cutting concerns — configuration, shared utilities |

## Frontend structure

```
frontend/src/
├── app/          # Next.js App Router pages and layouts
└── lib/          # Shared utilities (API client, helpers)
```

The frontend is a separate deployable unit. It communicates with the backend via REST over HTTP.

## Database

[Supabase](https://supabase.com) provides PostgreSQL, authentication, and storage. Schema migrations live in `supabase/migrations/`.

## SOLID mapping

| Principle | Application |
|-----------|-------------|
| **S** — Single Responsibility | Each layer and module has one reason to change |
| **O** — Open/Closed | Extend via new use cases and adapters, not by modifying domain |
| **L** — Liskov Substitution | Repository interfaces allow swapping persistence backends |
| **I** — Interface Segregation | Small, focused repository ports per aggregate |
| **D** — Dependency Inversion | Application depends on domain abstractions, not Supabase directly |

## What is not implemented yet

This foundation scaffold intentionally excludes business logic. Future work adds entities, use cases, and API endpoints following the same layer boundaries.
