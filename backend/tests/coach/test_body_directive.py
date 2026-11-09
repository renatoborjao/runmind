from app.application.coach.planning.body_directive import body_plan_directive
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_PERSISTING,
    TRAJ_STEADY,
    BodyTrajectory,
)
from app.domain.entities.training_load import TrainingLoad


def _reading(state, limiter="sono") -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=500.0, chronic_load=380.0, acwr=1.32,
            status="CAUTION", days_of_history=28,
        ),
        recovery=RecoveryTrend(days_covered=14),
        body_state=state,
        limiter=limiter,
    )


def _traj(movement=TRAJ_STEADY, streak=1) -> BodyTrajectory:

    return BodyTrajectory(
        movement=movement, alert_streak=streak, previous_state=None,
    )


def test_healthy_states_produce_no_directive():

    assert body_plan_directive(_reading(BODY_ABSORBING)) == ""
    assert body_plan_directive(_reading(BODY_BALANCED)) == ""


def test_strained_asks_the_coach_to_ease_and_not_the_athlete():

    directive = body_plan_directive(_reading(BODY_STRAINED))

    assert "COACH" in directive
    assert "NÃO pergunte ao atleta" in directive
    assert "RECUPERAÇÃO" in directive
    # limitador acionável presente
    assert "sono" in directive


def test_recovery_flag_weighs_against_capacity_not_a_blanket_brake():
    """RECOVERY_FLAG não é freio automático: manda PESAR contra a capacidade
    (limitador baseline que ele sustenta + carga tranquila -> não trava a
    progressão). Era o buraco do Mauricio (limiar de 15min com folga de tempo)."""

    directive = body_plan_directive(_reading(BODY_RECOVERY_FLAG))

    assert directive != ""
    # não manda cortar volume à toa (carga está ok)
    assert "à toa" in directive.lower()
    # convida a síntese em vez de um "evite subir" cego
    assert "capacidade" in directive.lower()
    assert "baseline" in directive.lower()
    assert "NÃO trave a progressão" in directive


def test_recovery_flag_persistence_points_to_learnings():
    """RECOVERY_FLAG que se repete: em vez de 'dá mais peso', manda CONFIRMAR nos
    aprendizados se é baseline (que ele sustenta) ou piora real."""

    directive = body_plan_directive(
        _reading(BODY_RECOVERY_FLAG),
        _traj(movement=TRAJ_PERSISTING, streak=3),
    )

    assert "3 leituras" in directive
    assert "APRENDIZADOS" in directive
    assert "BASELINE" in directive


def test_persistence_adds_weight():

    directive = body_plan_directive(
        _reading(BODY_STRAINED),
        _traj(movement=TRAJ_PERSISTING, streak=3),
    )

    assert "3 leituras seguidas" in directive


def test_no_persistence_note_when_not_persisting():

    directive = body_plan_directive(
        _reading(BODY_STRAINED), _traj(movement=TRAJ_STEADY, streak=0)
    )

    assert "leituras seguidas" not in directive


def test_recovery_flag_with_real_worsening_holds_with_hr_cap():
    """Varredura 26/09 (renato2): FC de repouso 59→70 e HRV 60→46 em 13
    leituras — piora REAL. A diretriz mostra a evidência e recomenda SEGURAR
    (não sobe, qualidade controlada, leve pelo teto de FC) em vez de 'não trave
    a progressão' — mas quem decide é a IA (sem regra fixa, 27/09)."""

    from app.application.history.training_patterns import RecoveryDrift

    drift = RecoveryDrift(
        rhr_now=70, rhr_base=59, hrv_now=46, hrv_base=60, alert_streak=13,
        sleep_avg=6.3, short_nights=6, nights=14,
    )

    text = body_plan_directive(
        _reading(BODY_RECOVERY_FLAG), _traj(TRAJ_PERSISTING, 13), drift, 151,
    )

    assert "PIORA REAL" in text and "SEGURAR a progressão" in text
    assert "decida" in text
    assert "59 → 70" in text and "151 bpm" in text
    assert "NÃO trave a progressão" not in text


def test_recovery_flag_stable_baseline_keeps_progression():

    from app.application.history.training_patterns import RecoveryDrift

    drift = RecoveryDrift(
        rhr_now=56, rhr_base=55, hrv_now=39, hrv_base=40, alert_streak=13,
        sleep_avg=6.0, short_nights=6, nights=14,
    )

    text = body_plan_directive(
        _reading(BODY_RECOVERY_FLAG), _traj(TRAJ_PERSISTING, 13), drift, 151,
    )

    assert "SEGURE" not in text
    assert "NÃO trave a progressão" in text


# ---- quem ENTREGA não é mandado aliviar; a queda que veio antes da carga não é sobrecarga ----


def test_strained_but_delivering_is_told_to_hold_what_he_absorbed_not_to_cut():

    text = body_plan_directive(_reading(BODY_STRAINED), delivering=True)

    assert "ENTREGOU o plano" in text and "SEGURAR o que ele absorveu" in text
    assert "dente de serra" in text
    assert "alivie o volume" not in text


def test_strained_without_delivery_keeps_the_old_instruction():

    text = body_plan_directive(_reading(BODY_STRAINED), delivering=False)

    assert "alivie o volume/intensidade desta semana" in text


def test_a_drop_that_came_before_the_load_rise_is_not_read_as_training_overload():

    from datetime import date

    reading = _reading(BODY_RECOVERY_FLAG)

    reading.alert_preceded_load = True

    reading.alert_since = date(2026, 10, 29)

    text = body_plan_directive(reading)

    assert "ORDEM" in text and "29/10" in text
    assert "não a causou" in text and "motivo pra cortar volume" in text


def test_the_hold_directive_also_carries_the_order_of_events():
    """Renato 08/11 (FC de repouso 62→67, HRV 58→45 desde 29/10): é piora REAL e o ramo é o de
    SEGURAR — e ele precisa dizer que a queda veio antes da carga subir."""

    from datetime import date

    from app.application.history.training_patterns import RecoveryDrift

    drift = RecoveryDrift(
        rhr_now=67, rhr_base=62, hrv_now=45, hrv_base=58, alert_streak=11,
        sleep_avg=6.0, short_nights=6, nights=14,
    )

    reading = _reading(BODY_RECOVERY_FLAG)

    reading.alert_preceded_load = True

    reading.alert_since = date(2026, 10, 29)

    text = body_plan_directive(reading, _traj(TRAJ_PERSISTING, 11), drift, 155)

    assert "PIORA REAL" in text and "SEGURAR a progressão" in text
    assert "ORDEM" in text and "29/10" in text and "não a causou" in text
