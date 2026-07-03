from fastapi import APIRouter, HTTPException

from app.application.history.history_analyzer import HistoryAnalyzer
from app.application.history.week_comparator import WeekComparator
from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.application.use_cases.activity_analyzer import ActivityAnalyzer
from app.application.use_cases.load_training_history import LoadTrainingHistory

router = APIRouter(
    prefix="/history",
    tags=["History"],
)


@router.get("")
async def training_history(limit: int = 30):

    try:

        history = await LoadTrainingHistory.execute(limit=limit)

        return ActivityAnalyzer.execute(history)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/analysis")
async def history_analysis(limit: int = 30):

    try:

        history = await LoadTrainingHistory.execute(limit=limit)

        return HistoryAnalyzer.analyze(history)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/weekly")
async def weekly_analysis(limit: int = 30):

    try:

        history = await LoadTrainingHistory.execute(limit=limit)

        return WeeklyVolumeAnalyzer.analyze(history)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/compare")
async def week_comparison(limit: int = 30):

    try:

        history = await LoadTrainingHistory.execute(limit=limit)

        return WeekComparator.compare(history)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )