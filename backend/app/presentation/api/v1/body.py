from fastapi import APIRouter, Depends, HTTPException

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/body", tags=["Body"])

_STATE = {
    "STRAINED": ("Sobrecarga", "bad"),
    "RECOVERY_FLAG": ("Recuperação em alerta", "warn"),
    "ABSORBING": ("Absorvendo a carga", "warn"),
    "BALANCED": ("Equilibrado", "good"),
    "FRESH": ("Descansado", "good"),
    "BUILDING": ("Construindo base", "good"),
}

_LIMITER = {
    "sono": "Sono",
    "hrv": "Variabilidade (HRV)",
    "fc_repouso": "FC de repouso",
    "carga": "Carga de treino",
    "carga_vida": "Movimento do dia",
    "stress": "Estresse",
}


@router.get("")
async def get_body(profile: str = Depends(current_profile)):
    """Leitura do corpo (determinística, sem IA, sem gravar): estado, limitador,
    ACWR e tendências de recuperação (HRV/FC/sono/etc.)."""

    try:

        reading, _ = BodyReadingService.read(profile, persist=False)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    rec = reading.recovery

    if not rec.has_data:

        return {"has_data": False}

    label, tone = _STATE.get(reading.body_state, (reading.body_state.title(), "warn"))

    return {
        "has_data": True,
        "body_state": reading.body_state,
        "state_label": label,
        "tone": tone,
        "limiter": reading.limiter,
        "limiter_label": _LIMITER.get(reading.limiter or "", None),
        "acwr": reading.load.acwr,
        "acwr_status": reading.load.status,
        "recovery": {
            "hrv_recent": rec.hrv_recent,
            "hrv_direction": rec.hrv_direction,
            "rhr_recent": rec.rhr_recent,
            "rhr_direction": rec.rhr_direction,
            "sleep_avg_hours": rec.sleep_avg_hours,
            "short_nights": rec.short_nights,
            "nights_counted": rec.nights_counted,
            "stress_avg": rec.stress_avg,
            "body_battery_wake": rec.body_battery_wake,
            "respiration_sleep": rec.respiration_sleep,
            "readiness_score": rec.readiness_score,
            "readiness_level": rec.readiness_level,
            "sleep_score": rec.sleep_score,
        },
    }
