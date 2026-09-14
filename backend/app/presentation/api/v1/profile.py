from fastapi import APIRouter, Depends, HTTPException

from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/profile", tags=["Profile"])

_DAY_PT = {
    "Monday": "Seg", "Tuesday": "Ter", "Wednesday": "Qua", "Thursday": "Qui",
    "Friday": "Sex", "Saturday": "Sáb", "Sunday": "Dom",
}


@router.get("")
async def get_profile(profile: str = Depends(current_profile)):
    """Dados do perfil do atleta logado."""

    try:

        r = RunnerProfileRepository().load(profile)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    parts = (r.name or "").strip().split(" ", 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""

    return {
        "id": r.id,
        "first_name": first,
        "last_name": last,
        "name": r.name,
        "email": r.email,
        "age": r.age,
        "weight": r.weight,
        "height": r.height,
        "sex": r.sex,
        "timezone": r.timezone,
        "goal": r.goal,
        "weekly_training_days": r.weekly_training_days,
        "preferred_running_days": [
            _DAY_PT.get(d, d) for d in (r.preferred_running_days or [])
        ],
        "target_race": r.target_race,
        "race_date": r.race_date,
        "target_time": r.target_time,
    }
