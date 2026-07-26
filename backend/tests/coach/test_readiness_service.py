import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.coach.intelligence.readiness_evaluator import (
    DEMAND_DEMANDING,
)
from app.application.coach.intelligence.readiness_service import (
    ReadinessService,
)
from app.domain.entities.body_reading import (
    BODY_BALANCED,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.readiness_verdict import (
    READINESS_BRAKE,
    READINESS_NEUTRAL,
)
from app.domain.entities.training_load import TrainingLoad
from app.infrastructure.persistence.readiness_diary_repository import (
    ReadinessDiaryRepository,
)

MOD = "app.application.coach.intelligence.readiness_service"


def _reading(state) -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=500.0, chronic_load=380.0, acwr=1.31,
            status="CAUTION", days_of_history=28,
        ),
        recovery=RecoveryTrend(days_covered=14),
        body_state=state,
        limiter="sono",
    )


def _evaluate_sequence(tmp_path, states):
    """Roda ReadinessService.evaluate uma vez por estado, com tudo mockado
    menos o avaliador e o dedup reais. Devolve as entradas gravadas."""

    runner = SimpleNamespace(timezone="America/Sao_Paulo")

    repo = ReadinessDiaryRepository()
    repo.storage = tmp_path

    entries = []

    with (
        patch(f"{MOD}.LoadRunnerProfile") as lrp,
        patch(f"{MOD}.CurrentPlanProvider") as cpp,
        patch(f"{MOD}.BodyReadingService") as brs,
        patch(f"{MOD}.ReadinessDiaryRepository", return_value=repo),
        patch.object(
            ReadinessService, "_todays_demand", return_value=DEMAND_DEMANDING
        ),
    ):

        lrp.execute.return_value = runner
        cpp.for_profile = AsyncMock(return_value=(runner, object()))

        for state in states:

            brs.read.return_value = (_reading(state), None)

            _verdict, entry = asyncio.run(
                ReadinessService.evaluate("renato2")
            )

            entries.append(entry)

    return entries


def test_fala_na_virada_e_cala_na_persistencia(tmp_path):

    # STRAINED novo → fala; STRAINED de novo → cala (mesmo estado)
    entries = _evaluate_sequence(
        tmp_path, [BODY_STRAINED, BODY_STRAINED]
    )

    assert entries[0].tier == READINESS_BRAKE
    assert entries[0].would_notify is True
    assert entries[0].from_tier is None

    assert entries[1].tier == READINESS_BRAKE
    assert entries[1].would_notify is False        # persistiu → não repete
    assert entries[1].from_tier == READINESS_BRAKE


def test_neutro_nunca_fala_mas_arma_a_virada(tmp_path):

    # BALANCED (nada) → depois STRAINED (virada) → fala
    entries = _evaluate_sequence(
        tmp_path, [BODY_BALANCED, BODY_STRAINED]
    )

    assert entries[0].tier == READINESS_NEUTRAL
    assert entries[0].would_notify is False

    assert entries[1].tier == READINESS_BRAKE
    assert entries[1].would_notify is True         # NEUTRAL → BRAKE = virada
    assert entries[1].from_tier == READINESS_NEUTRAL


# --- resolução da exigência do treino de hoje ---------------------------


class _FakePlan:

    def __init__(self, sessions, dates):
        self.sessions = sessions
        self._dates = dict(zip(map(id, sessions), dates))

    def session_date(self, session):
        return self._dates[id(session)]


def _session(workout_type) -> PlannedSession:

    return PlannedSession(
        day="tuesday", workout_type=workout_type, objective="",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None,
    )


def test_demanda_exigente_leve_descanso_desconhecido():

    from datetime import date

    today = date(2026, 7, 28)

    tiro = _session("Tiros 5x800")
    rodagem = _session("Rodagem leve")

    assert ReadinessService._todays_demand(
        _FakePlan([tiro], [today]), today
    ) == "demanding"

    assert ReadinessService._todays_demand(
        _FakePlan([rodagem], [today]), today
    ) == "easy"

    # sessão só amanhã → hoje é descanso
    assert ReadinessService._todays_demand(
        _FakePlan([tiro], [date(2026, 7, 29)]), today
    ) == "rest"

    # sem plano casável
    assert ReadinessService._todays_demand(
        _FakePlan([], []), today
    ) == "unknown"
