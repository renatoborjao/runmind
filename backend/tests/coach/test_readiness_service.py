import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.coach.intelligence.readiness_evaluator import (
    DEMAND_DEMANDING,
    DEMAND_REST,
)
from app.application.coach.intelligence.readiness_service import (
    ReadinessService,
)
from app.domain.entities.body_reading import (
    BODY_BALANCED,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.readiness_diary_entry import ReadinessDiaryEntry
from app.domain.entities.readiness_verdict import (
    READINESS_BRAKE,
    READINESS_CAUTION,
    READINESS_GREEN,
    READINESS_NEUTRAL,
    ReadinessVerdict,
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


# --- cadência de ORIENTAÇÃO: _is_new_orientation (função pura) -----------
# o coach orienta, não repete: fala no 1º dia de decisão do episódio de alerta
# e quando PIORA; cala nas repetições. Ver [[feedback_orientar_nao_mandar]].


def _diary(tier, would_notify, day="2026-07-01") -> ReadinessDiaryEntry:

    return ReadinessDiaryEntry(
        day=day, at=f"{day}T09:00:00-03:00", tier=tier,
        body_state="X", reason="", demand=DEMAND_DEMANDING,
        would_notify=would_notify,
    )


def _verdict(tier) -> ReadinessVerdict:

    return ReadinessVerdict(
        tier=tier, reason="", should_speak=True, body_state="X",
    )


def test_orientacao_primeiro_dia_do_episodio_mesmo_sem_virada():

    # episódio de alerta com dias silenciosos (descanso, nunca falamos) → o 1º
    # dia de DECISÃO fala mesmo sem virada de tier — o furo da régua antiga
    # (caso Fernanda: cronicamente CAUTION, calava justo no dia puxado).
    history = [
        _diary(READINESS_CAUTION, False),
        _diary(READINESS_CAUTION, False),
    ]

    assert ReadinessService._is_new_orientation(
        history, _verdict(READINESS_CAUTION)
    ) is True


def test_orientacao_nao_repete_no_mesmo_episodio():

    # já falamos neste episódio de CAUTION → não repete (nada de nagging)
    assert ReadinessService._is_new_orientation(
        [_diary(READINESS_CAUTION, True)], _verdict(READINESS_CAUTION)
    ) is False


def test_orientacao_volta_a_falar_quando_piora():

    # falamos em CAUTION, agora BRAKE (piorou) → notícia nova, re-orienta
    assert ReadinessService._is_new_orientation(
        [_diary(READINESS_CAUTION, True)], _verdict(READINESS_BRAKE)
    ) is True


def test_orientacao_brake_persistente_nao_repete():

    assert ReadinessService._is_new_orientation(
        [_diary(READINESS_BRAKE, True)], _verdict(READINESS_BRAKE)
    ) is False


def test_orientacao_dia_sem_alerta_encerra_o_episodio():

    # falou no episódio anterior, recuperou (NEUTRAL quebra o streak), voltou
    # ao alerta → decisão NOVA → fala de novo
    history = [
        _diary(READINESS_CAUTION, True),
        _diary(READINESS_NEUTRAL, False),
    ]

    assert ReadinessService._is_new_orientation(
        history, _verdict(READINESS_CAUTION)
    ) is True


def test_orientacao_verde_fala_ao_entrar_e_nao_repete():

    # verde: fala ao ENTRAR no estado, cala na repetição
    assert ReadinessService._is_new_orientation(
        [_diary(READINESS_NEUTRAL, False)], _verdict(READINESS_GREEN)
    ) is True

    assert ReadinessService._is_new_orientation(
        [_diary(READINESS_GREEN, True)], _verdict(READINESS_GREEN)
    ) is False


def _evaluate_pairs(tmp_path, pairs):
    """Como _evaluate_sequence, mas cada item é (state, demand) — pra simular
    dias de descanso (o vigia cala) intercalados com dias puxados."""

    runner = SimpleNamespace(timezone="America/Sao_Paulo")

    repo = ReadinessDiaryRepository()
    repo.storage = tmp_path

    entries = []
    demands = iter(d for _, d in pairs)

    with (
        patch(f"{MOD}.LoadRunnerProfile") as lrp,
        patch(f"{MOD}.CurrentPlanProvider") as cpp,
        patch(f"{MOD}.BodyReadingService") as brs,
        patch(f"{MOD}.ReadinessDiaryRepository", return_value=repo),
        patch.object(
            ReadinessService, "_todays_demand",
            side_effect=lambda *a, **k: next(demands),
        ),
    ):

        lrp.execute.return_value = runner
        cpp.for_profile = AsyncMock(return_value=(runner, object()))

        for state, _demand in pairs:

            brs.read.return_value = (_reading(state), None)

            _verdict_out, entry = asyncio.run(
                ReadinessService.evaluate("fernanda")
            )

            entries.append(entry)

    return entries


def test_alerta_cronico_fala_no_dia_puxado_apos_descanso(tmp_path):

    # caso Fernanda ponta-a-ponta: RECOVERY_FLAG em dia de descanso (cala) e,
    # no dia puxado seguinte, o vigia FALA — mesmo sem virada de tier.
    entries = _evaluate_pairs(
        tmp_path,
        [
            (BODY_RECOVERY_FLAG, DEMAND_REST),
            (BODY_RECOVERY_FLAG, DEMAND_DEMANDING),
        ],
    )

    assert entries[0].tier == READINESS_CAUTION
    assert entries[0].would_notify is False        # descanso → nada a conduzir

    assert entries[1].tier == READINESS_CAUTION
    assert entries[1].would_notify is True          # dia puxado → orienta


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
