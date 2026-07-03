from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.infrastructure.scheduling.weekly_plan_scheduler import (
    start_weekly_plan_scheduler,
    stop_weekly_plan_scheduler,
)
from app.presentation.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_weekly_plan_scheduler()
    yield
    stop_weekly_plan_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="RunMind API",
        description="The AI-powered platform for runners.",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()
