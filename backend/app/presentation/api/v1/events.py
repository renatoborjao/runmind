from fastapi import APIRouter, HTTPException

from app.application.events.training_completed import (
    TrainingCompletedEvent,
)

router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


@router.post("/training-completed")
async def training_completed():

    try:

        message = await TrainingCompletedEvent.execute()

        return {

            "status": "success",

            "message": message,

        }

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e),

        )