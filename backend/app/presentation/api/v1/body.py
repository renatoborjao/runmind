from fastapi import APIRouter, Depends, HTTPException

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/body", tags=["Body"])


def _trend(profile: str) -> dict | None:
    """Série dos últimos 7 dias COM dado, pra desenhar as tendências de
    recuperação (sparklines). Só entra métrica que tem pelo menos 2 pontos reais
    na janela — o resto vem None e o app esconde. Nada é calculado aqui: é só a
    série crua que o Garmin já gravou."""

    days = [h for h in GarminHealthRepository().load(profile) if h.has_data][-7:]

    if len(days) < 2:

        return None

    dates = [h.date for h in days]

    def series(attr: str) -> list[float | None] | None:

        vals = [getattr(h, attr) for h in days]

        real = [v for v in vals if v is not None]

        return vals if len(real) >= 2 else None

    return {
        "dates": dates,
        "readiness": series("readiness_score"),
        "battery": series("body_battery_at_wake"),
        "sleep_hours": series("sleep_hours"),
        "resting_hr": series("resting_hr"),
        "hrv": series("hrv_last_night"),
    }

def _sleep(profile: str) -> dict | None:
    """Detalhe da ÚLTIMA noite medida + as últimas 7 noites (pro gráfico semanal
    de barras por estágio, à la Garmin). Só dado cru do relógio, sem cálculo.
    None quando não há nenhuma noite com sono. Estágios podem vir None em relógio
    básico (o app esconde o que não veio)."""

    series = GarminHealthRepository().load(profile)

    with_sleep = [h for h in series if h.sleep_hours is not None]

    if not with_sleep:

        return None

    h = with_sleep[-1]

    # últimas 7 noites com sono, pro gráfico semanal (mais antiga → mais recente)
    nights = [
        {
            "date": n.date,
            "hours": n.sleep_hours,
            "score": n.sleep_score,
            "deep": n.deep_sleep_hours,
            "light": n.light_sleep_hours,
            "rem": n.rem_sleep_hours,
            "awake": n.awake_hours,
        }
        for n in with_sleep[-7:]
    ]

    return {
        "date": h.date,
        "hours": h.sleep_hours,
        "score": h.sleep_score,
        "deep": h.deep_sleep_hours,
        "light": h.light_sleep_hours,
        "rem": h.rem_sleep_hours,
        "awake": h.awake_hours,
        "respiration": h.respiration_sleep_avg,
        "spo2": h.spo2_sleep_avg,
        "nights": nights,
    }


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
    """Leitura do corpo: estado/limitador/ACWR/tendências são determinísticos
    (sem IA, sem gravar); a narrativa é gerada pela IA a partir do veredito já
    calculado, com cache de 1x/dia (persistida) e fallback determinístico se a
    IA falhar."""

    try:

        reading, trajectory = BodyReadingService.read(profile, persist=False)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    rec = reading.recovery

    if not rec.has_data:

        return {"has_data": False}

    label, tone = _STATE.get(reading.body_state, (reading.body_state.title(), "warn"))

    try:

        runner_name = RunnerProfileRepository().load(profile).name or profile

        narrative = await BodyReadingService.narrative_for(
            profile, runner_name, reading, trajectory
        )

    except Exception as e:

        print(f"Narrativa da leitura do corpo falhou p/ '{profile}': {e}")

        narrative = None

    try:

        trend = _trend(profile)

    except Exception:

        trend = None

    try:

        sleep = _sleep(profile)

    except Exception:

        sleep = None

    return {
        "has_data": True,
        "trend": trend,
        "sleep": sleep,
        "body_state": reading.body_state,
        "state_label": label,
        "tone": tone,
        "narrative": narrative,
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
