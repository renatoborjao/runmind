from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.application.coach.summary.coach_summary_builder import (
    CoachSummaryBuilder,
)
from app.application.coach.writer.coach_writer import CoachWriter
from app.application.orchestrators.coach_analysis_builder import (
    CoachAnalysisBuilder,
)
from app.presentation.schemas.mappers import to_activity_response

router = APIRouter(
    prefix="/insights",
    tags=["Insights"],
)


@router.get("/latest")
async def latest_insights():

    try:

        result = await CoachAnalysisBuilder.build()

        enriched = result["enriched"]

        analysis = result["analysis"]

        summary = CoachSummaryBuilder.build(
            result["runner"].name,
            analysis,
        )

        message = CoachWriter.write(
            result["context"],
            summary,
        )

        return {
            "activity": to_activity_response(
                enriched.activity,
            ),
            "enrichment": {
                "pace_min_km": enriched.pace_min_km,
                "training_type": enriched.training_type,
                "intensity": enriched.intensity,
                "estimated_zone": enriched.estimated_zone,
                "training_load": enriched.training_load,
                "fatigue_score": enriched.fatigue_score,
                "recovery_hours": enriched.recovery_hours,
            },
            "analysis": asdict(analysis),
            "message": asdict(message),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
