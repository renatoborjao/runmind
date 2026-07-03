from fastapi import APIRouter, HTTPException

from app.application.use_cases.analyze_activity import AnalyzeActivity
from app.infrastructure.integrations.strava.client import StravaClient

router = APIRouter(
    prefix="/activities",
    tags=["Activities"],
)


@router.get("/latest")
async def latest_activity():

    client = StravaClient()

    try:

        activity = await client.get_latest_activity()

        if activity is None:
            raise HTTPException(
                status_code=404,
                detail="Nenhuma atividade encontrada.",
            )

        return AnalyzeActivity.execute(activity)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )