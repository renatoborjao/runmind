from fastapi import APIRouter, HTTPException, Query

from app.application.history.evolution_analyzer import EvolutionAnalyzer
from app.application.use_cases.load_training_history import LoadTrainingHistory

# per_page máximo da API do Strava
MAX_ACTIVITIES = 200

router = APIRouter(
    prefix="/evolution",
    tags=["Evolution"],
)


@router.get("")
async def evolution(weeks: int = Query(default=12, ge=1, le=26)):

    try:

        limit = min(MAX_ACTIVITIES, weeks * 7)

        history = await LoadTrainingHistory.execute(limit=limit)

        return EvolutionAnalyzer.analyze(history, weeks=weeks)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
