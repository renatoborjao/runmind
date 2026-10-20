"""ESPAÇO PRA PUXAR — o espelho da descarga. Renato, 19/10: "não quero nosso coach
extremamente conservador; se der para puxar, tem que puxar". O coach só via os freios
(+5-10%, "segurança primeiro") e repetia a semana. Agora, com o plano cumprido, a
recuperação firme e a carga sob controle, o dossiê diz que há folga e traz os km."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.coach.context.athlete_dossier import AthleteDossier
from app.application.history.push_room import (
    PushRoom,
    PushRoomAnalyzer,
    push_room_directive,
    push_room_fact,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    STABLE,
    RecoveryTrend,
)
from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_STABLE,
)
from tests.coach.factories import make_activity


def _recovery(hrv=STABLE, rhr=STABLE) -> RecoveryTrend:

    return RecoveryTrend(hrv_direction=hrv, rhr_direction=rhr, days_covered=7)


def _assess(adherence=(1.0, 1.0), recovery=None, **kwargs):

    return PushRoomAnalyzer.assess(
        list(adherence), recovery or _recovery(), **kwargs,
    )


# ---- quando há folga -------------------------------------------------------------


def test_the_room_opens_when_the_plan_is_done_and_the_body_is_firm():
    """Maurício 19/10: carga 290, ACWR 0,93, recuperação estável, cumprindo."""

    room = _assess(body_state=BODY_BALANCED, form=EVO_STABLE, acwr=0.93)

    assert room.open is True
    assert room.adherence == 1.0
    assert room.weeks == 2


def test_a_fresh_or_improving_athlete_has_room():

    assert _assess(body_state=BODY_FRESH, form=EVO_IMPROVING, acwr=0.7).open is True
    assert _assess(body_state=BODY_ABSORBING, acwr=1.25).open is True


def test_adherence_of_ninety_percent_on_average_is_enough():

    assert _assess(adherence=(0.8, 1.0)).open is True   # média 90%
    assert _assess(adherence=(0.8, 0.9)).open is False  # média 85%


# ---- quando NÃO há ------------------------------------------------------------------


def test_no_room_without_proof_of_execution():

    room = _assess(adherence=())

    assert room.open is False
    assert "sem execução recente" in room.reason


def test_no_room_when_the_plan_is_not_being_done():

    room = _assess(adherence=(0.5, 0.6))

    assert room.open is False
    assert "cumprindo" in room.reason


def test_no_room_when_the_recovery_is_falling():

    for recovery in (_recovery(hrv=FALLING), _recovery(rhr=FALLING)):

        assert _assess(recovery=recovery).open is False

    assert _assess(body_state=BODY_STRAINED).open is False
    assert _assess(body_state=BODY_RECOVERY_FLAG).open is False


def test_no_room_when_the_form_dropped_or_the_load_shot_up():

    assert _assess(form=EVO_DECLINING).open is False

    room = _assess(acwr=1.43)

    assert room.open is False
    assert "carga já subiu" in room.reason

    assert _assess(acwr=1.3).open is True  # no limite da faixa saudável


def test_no_room_with_injury_risk_or_an_open_illness():

    assert _assess(injury_risk=True).open is False
    assert _assess(ill=True).open is False


def test_no_room_when_the_race_owns_the_load():
    """Taper e pós-prova mandam na carga — nada de empurrar."""

    assert _assess(weeks_to_race=2).open is False
    assert _assess(weeks_since_race=1).open is False
    assert _assess(weeks_to_race=2, taper_zone_weeks=1).open is True


# ---- o que o coach lê ------------------------------------------------------------------


def test_the_directive_is_silent_without_room():

    assert push_room_directive(PushRoom(False, "x")) == ""


def test_the_directive_states_the_facts_the_step_and_the_only_ceiling():

    room = PushRoom(True, "ok", 0.95, 2)

    text = push_room_directive(room, " Números reais: melhor semana ~47 km.")

    assert text.startswith("ESPAÇO PRA PUXAR")
    assert "95% do plano nas últimas 2 semanas" in text
    assert "Números reais: melhor semana ~47 km" in text
    assert "+10%" in text and "~15%" in text
    assert "não pra repetir a semana anterior" in text
    # o passo parte do que o atleta CORREU (Maurício executa acima do plano)
    assert "REALMENTE correu" in text and "o plano que ficou baixo" in text


def test_the_directive_asks_for_quality_in_every_kind_of_session_not_just_the_long_run():
    """Renato: o foco não é só o longão — é subir a qualidade em TODOS os tipos de
    treino, sempre rumo à meta; o leve continua leve."""

    text = push_room_directive(PushRoom(True, "ok", 1.0, 2))

    assert "TODOS os tipos de treino, não só no longão" in text
    assert "o forte chega mais perto do ritmo-alvo" in text
    assert "o moderado alonga" in text
    assert "o leve continua leve DE VERDADE" in text
    assert "nunca vira mais um forte" in text
    assert "rumo à meta do atleta" in text
    # o único teto: o salto
    assert "SALTO" in text and "+25%" in text
    assert "A dose e a forma são suas" in text


def test_the_directive_for_a_single_week():

    text = push_room_directive(PushRoom(True, "ok", 1.0, 1))

    assert "na última semana" in text


# ---- no dossiê -------------------------------------------------------------------------


def _data():

    return SimpleNamespace(
        profile="mauricio",
        history=SimpleNamespace(activities=[]),
        runner=SimpleNamespace(),
        reading=SimpleNamespace(recovery=_recovery(), body_state=BODY_BALANCED),
    )


BASE = SimpleNamespace(weekly_km=38.4, last_week_km=37.0, max_week_km=47.2, longest_km=14.9)


def _week_runs(*weeks):
    """Corridas reais (sem plano) nas semanas 05/10, 12/10, 19/10: uma lista de km
    por semana."""

    runs, serial = [], 0

    for monday, kms in zip((date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19)), weeks):

        for i, km in enumerate(kms):

            serial += 1

            runs.append(
                make_activity(
                    id=serial, distance=km * 1000.0,
                    start_date=datetime(2026, monday.month, monday.day + i, 7, 0, 0),
                )
            )

    return runs


def _push(data=None, adherence=(1.0, 1.0), ill=None, **kwargs):

    args = {
        "weeks_to_race": None, "weeks_since_race": None, "taper_zone": None,
        "acwr": 0.93, "form": EVO_STABLE, "risk": None,
    }

    args.update(kwargs)

    with (
        patch(
            "app.application.planner.weekly_plan_service.WeeklyPlanService."
            "_recent_adherence",
            return_value=list(adherence),
        ),
        patch(
            "app.application.history.runner_baseline_builder.RunnerBaselineBuilder."
            "build",
            return_value=BASE,
        ),
        patch.object(AthleteDossier, "_open_illness", return_value=ill),
    ):

        return AthleteDossier._push_room(
            data or _data(), date(2026, 10, 26), **args,
        )


def test_the_dossier_carries_the_real_km_of_the_closed_weeks_when_there_is_room():
    """Maurício: 39, 43 e 47 km nas 3 semanas fechadas antes de 26/10 — a semana em
    andamento NÃO entra pela metade."""

    data = _data()

    data.history = SimpleNamespace(
        activities=_week_runs([15, 12, 12], [14, 15, 14], [20, 15, 12])
        + [make_activity(id=99, distance=4200.0, start_date=datetime(2026, 10, 26, 7, 0, 0))],
    )

    text = _push(data)

    assert text.startswith("ESPAÇO PRA PUXAR")
    assert "nas últimas 3 semanas fechadas correu 39, 43 e 47 km" in text
    assert "melhor semana ~47 km" in text
    assert "maior treino recente ~15 km" in text


def test_the_dossier_skips_the_closed_weeks_when_there_is_no_run_history():

    text = _push()

    assert text.startswith("ESPAÇO PRA PUXAR")
    assert "nas últimas 3 semanas fechadas correu" not in text
    assert "melhor semana ~47 km" in text


def test_the_dossier_is_silent_without_room():

    assert _push(adherence=(0.4, 0.5)) == ""
    assert _push(ill=SimpleNamespace(day="2026-10-20")) == ""
    assert _push(risk=SimpleNamespace(level="ELEVATED")) == ""
    assert _push(acwr=1.6) == ""


def test_the_low_base_mark_is_read_like_the_injury_analyzer_does():
    """tuple (min/semana da base, min a mais) = razão alta só pela base baixa."""

    marked = SimpleNamespace(load=SimpleNamespace(low_base=(46, 12)))
    plain = SimpleNamespace(load=SimpleNamespace(low_base=None))
    missing = SimpleNamespace(load=SimpleNamespace())

    assert AthleteDossier._is_low_base(marked) is True
    assert AthleteDossier._is_low_base(plain) is False
    assert AthleteDossier._is_low_base(missing) is False


def test_a_failure_in_the_push_signal_never_breaks_the_dossier():

    with patch(
        "app.application.planner.weekly_plan_service.WeeklyPlanService."
        "_recent_adherence",
        side_effect=OSError("disco"),
    ):

        assert AthleteDossier._push_room(
            _data(), date(2026, 10, 26), None, None, None, 0.9, None, None,
        ) == ""


# ---- fato × instrução: cada voz recebe o que serve a ela (dossiê só com fatos) -----------------


def test_the_fact_is_short_and_has_no_dose_instruction():
    """Chat, análise, resumos e nutrição leem a mesma base: o FATO, sem o "passo de ~+10%"."""

    room = PushRoom(True, "ok", 1.0, 2)

    fact = push_room_fact(room, " Números reais: melhor semana ~47 km.")

    assert fact == (
        "Folga pra progredir: cumpriu 100% do plano nas últimas 2 semanas, a recuperação "
        "está firme e a forma não recuou. Números reais: melhor semana ~47 km."
    )
    for instruction in ("+10%", "~15%", "SALTO", "PUXE", "A dose e a forma são suas"):

        assert instruction not in fact

    # o texto do plano é bem maior: é o que deixava de vazar pras outras vozes
    assert len(push_room_directive(room)) > 3 * len(push_room_fact(room))


def test_the_fact_is_silent_without_room_and_counts_one_week():

    assert push_room_fact(PushRoom(False, "x")) == ""
    assert "na última semana" in push_room_fact(PushRoom(True, "ok", 0.9, 1))


def test_the_dossier_gives_the_plan_the_instruction_and_the_others_the_fact():

    plan_text = _push(plan_voice=True)
    other_text = _push(plan_voice=False)

    assert plan_text.startswith("ESPAÇO PRA PUXAR")
    assert "passo-padrão é ~+10%" in plan_text

    assert other_text.startswith("Folga pra progredir")
    assert "+10%" not in other_text and "SALTO" not in other_text
    # os números reais seguem nas duas
    assert "melhor semana ~47 km" in plan_text and "melhor semana ~47 km" in other_text
    assert len(other_text) < len(plan_text) / 2
