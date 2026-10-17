"""DESAQUECIMENTO ABERTO não é estouro de volume. Caso real do Renato (17/10): o plano
dizia Longão 12 km = aquecimento 2 km + contínuo 10 km + desaquecimento SEM distância;
ele fez os 2 km de desaquecimento (14,01 km no total) e a análise o acusou de "14 km
contra 12" e de "fugir totalmente do planejado" — o desvio real era o ritmo/FC do bloco
principal, não os 2 km soltos no fim."""

from unittest.mock import patch

from app.application.coach.intelligence.distance_intelligence import (
    DistanceIntelligence,
)
from app.application.coach.signals.codes import DistanceStatus
from app.application.coach.writer.ai_analysis_writer import AIAnalysisWriter
from app.domain.entities.block_comparison import BlockComparison, ExecutedBlock
from app.domain.entities.workout_step import (
    COOLDOWN,
    RUN,
    WARMUP,
    WorkoutStep,
    has_open_cooldown,
)
from tests.coach.factories import (
    make_activity,
    make_context,
    make_enriched_activity,
    make_planned_session,
)


def _steps(cooldown_m=None):

    return [
        WorkoutStep(kind=WARMUP, distance_m=2000, pace_min="6:30", pace_max="6:45"),
        WorkoutStep(kind=RUN, distance_m=10000, pace_min="6:20", pace_max="6:35", hr_max=154),
        WorkoutStep(kind=COOLDOWN, distance_m=cooldown_m),
    ]


def _block(kind, planned_m, executed_m):

    return ExecutedBlock(
        kind=kind, label=kind, planned_distance_m=planned_m, planned_duration_sec=None,
        pace_min=None, pace_max=None, executed_distance_m=executed_m,
        executed_duration_sec=600, executed_pace=6.0, executed_hr=150,
    )


def _renato_context(cooldown_m=None, comparison=True, executed_km=14.01):

    blocks = [
        _block(WARMUP, 2000, 2000.0),
        _block(RUN, 10000, 10000.0),
        _block(COOLDOWN, cooldown_m, 2009.0),
    ]

    return make_context(
        planned=make_planned_session(
            workout_type="Longão", planned_distance_km=12.0, steps=_steps(cooldown_m),
        ),
        executed=make_enriched_activity(
            activity=make_activity(distance=executed_km * 1000),
        ),
        block_comparison=BlockComparison(blocks=blocks) if comparison else None,
    )


# ---- o passo ---------------------------------------------------------------


def test_has_open_cooldown():

    assert has_open_cooldown(_steps(None)) is True
    assert has_open_cooldown(_steps(1000)) is False
    assert has_open_cooldown([WorkoutStep(kind=RUN, distance_m=5000)]) is False
    assert has_open_cooldown([]) is False

    # desaquecimento aberto dentro de um grupo que repete
    nested = [WorkoutStep(kind="repeat", reps=2, steps=_steps(None))]

    assert has_open_cooldown(nested) is True


# ---- a inteligência de distância ---------------------------------------------


def test_renato_14km_with_an_open_cooldown_is_on_plan():
    """14,01 km executados, mas 2,009 km foram o desaquecimento livre: o volume até o
    bloco principal é ~12,0 km = o planejado."""

    finding = DistanceIntelligence.process(_renato_context())

    assert finding.code == DistanceStatus.OK.value
    assert abs(finding.params["delta_percent"]) <= 1
    # o total real continua visível e o desaquecimento vem à parte
    assert finding.params["executed_km"] == 14.0
    assert finding.params["open_cooldown_km"] == 2.0


def test_open_cooldown_without_lap_data_never_accuses_an_overshoot():
    """Sem as voltas pareadas (sem Garmin) não dá pra separar o desaquecimento do
    resto: não acusa 'acima do plano'."""

    finding = DistanceIntelligence.process(_renato_context(comparison=False))

    assert finding.code == DistanceStatus.OK.value


def test_open_cooldown_still_flags_a_short_session():
    """Correu bem menos do que o prescrito: segue 'abaixo do plano'."""

    finding = DistanceIntelligence.process(
        _renato_context(comparison=False, executed_km=9.0)
    )

    assert finding.code == DistanceStatus.BELOW.value


def test_closed_cooldown_overshoot_is_still_an_overshoot():
    """Regressão: com desaquecimento FECHADO (distância no plano), 14 km num treino de
    12 km continua sendo 'acima do plano'."""

    finding = DistanceIntelligence.process(_renato_context(cooldown_m=2000))

    assert finding.code == DistanceStatus.ABOVE.value


def test_session_without_steps_behaves_as_before():

    context = make_context(
        planned=make_planned_session(planned_distance_km=12.0),
        executed=make_enriched_activity(activity=make_activity(distance=14010.0)),
    )

    assert DistanceIntelligence.process(context).code == DistanceStatus.ABOVE.value


# ---- os fatos que a IA lê ----------------------------------------------------


def test_the_analysis_facts_tell_the_ai_the_cooldown_is_free():

    with patch(
        "app.application.coach.context.athlete_dossier.AthleteDossier.render",
        return_value="",
    ):

        facts = AIAnalysisWriter._facts(_renato_context())

    assert "Planejado: Longão — 12.0 km + desaquecimento livre" in facts
    assert "Desaquecimento LIVRE" in facts
    assert "NÃO contam como volume acima do planejado" in facts


def test_the_facts_are_unchanged_when_the_cooldown_has_a_distance():

    with patch(
        "app.application.coach.context.athlete_dossier.AthleteDossier.render",
        return_value="",
    ):

        facts = AIAnalysisWriter._facts(_renato_context(cooldown_m=2000))

    assert "desaquecimento livre" not in facts
    assert "Desaquecimento LIVRE" not in facts
