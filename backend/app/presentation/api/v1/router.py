from fastapi import APIRouter

from app.presentation.api.v1 import activities
from app.presentation.api.v1 import debug
from app.presentation.api.v1 import events
from app.presentation.api.v1 import evolution
from app.presentation.api.v1 import health
from app.presentation.api.v1 import history
from app.presentation.api.v1 import insights
from app.presentation.api.v1 import plan
from app.presentation.api.v1 import strava
from app.presentation.api.v1 import webhooks

router = APIRouter()

router.include_router(health.router)

router.include_router(strava.router)

router.include_router(webhooks.router)

router.include_router(activities.router)

router.include_router(history.router)

router.include_router(evolution.router)

router.include_router(insights.router)

router.include_router(plan.router)

router.include_router(debug.router)

router.include_router(events.router)