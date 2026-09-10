"""Aderência de ESTÍMULO: o atleta correu na faixa-alvo que o coach prescreveu,
ou só apareceu no dia e trotou? Presença já é medida em outro lugar; aqui é o
ritmo — o que separa 'seguir o plano' de 'treinar aleatório'."""

from datetime import date, datetime, timedelta

from app.application.history.stimulus_adherence import (
    NO_TARGET,
    ON_TARGET,
    STRUCTURED,
    TOO_FAST,
    TOO_SLOW,
    StimulusAdherence,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import WorkoutStep
from tests.coach.factories import make_activity

WEEK = date(2026, 7, 20)  # segunda
REFERENCE = WEEK + timedelta(days=6)  # domingo que fecha a semana

_DAY_OFFSET = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


def _session(day, tmin=None, tmax=None, steps=None, distance=6.0):

    return PlannedSession(
        day=day,
        workout_type="Rodagem",
        objective="",
        planned_distance_km=distance,
        planned_duration_minutes=None,
        target_pace_min=tmin,
        target_pace_max=tmax,
        kind="run",
        steps=steps or [],
    )


def _plan(sessions):

    return TrainingPlan(
        athlete_name="X",
        objective="10k",
        phase="BASE",
        weekly_volume=18.0,
        running_days=[s.day for s in sessions],
        week_start=WEEK,
        sessions=sessions,
    )


def _run_at_pace(day, pace_sec, activity_id, distance_km=6.0):
    """Corrida no dia pedido, com pace médio = pace_sec s/km."""

    when = WEEK + timedelta(days=_DAY_OFFSET[day])

    return make_activity(
        id=activity_id,
        start_date=datetime(when.year, when.month, when.day, 7, 0, 0),
        distance=distance_km * 1000,
        moving_time=int(pace_sec * distance_km),
    )


def _analyze(plan, activities):

    return StimulusAdherence.analyze(
        [plan],
        TrainingHistory(activities),
        until_week=WEEK,
        reference_date=REFERENCE,
    )


def test_dentro_da_faixa_e_on_target():
    # alvo 6:20–6:45; correu 6:38 → executou o estímulo
    report = _analyze(
        _plan([_session("Tuesday", "6:20", "6:45")]),
        [_run_at_pace("Tuesday", 398, 1)],
    )

    assert [s.verdict for s in report.sessions] == [ON_TARGET]

    assert report.rate == 1.0


def test_trotou_no_dia_do_ritmo_e_too_slow():
    # alvo 5:30–5:45; foi no dia e correu 6:40 → pegou leve (o caso do Renato)
    report = _analyze(
        _plan([_session("Tuesday", "5:30", "5:45")]),
        [_run_at_pace("Tuesday", 400, 1)],
    )

    session = report.sessions[0]

    assert session.verdict == TOO_SLOW

    assert session.delta_sec == 400 - 345  # 55 s/km mais lento que o teto

    assert report.rate == 0.0


def test_forcou_alem_no_dia_leve_e_too_fast():
    # alvo 6:20–6:45 (leve/descarga); correu 5:40 → forçou além
    report = _analyze(
        _plan([_session("Tuesday", "6:20", "6:45")]),
        [_run_at_pace("Tuesday", 340, 1)],
    )

    session = report.sessions[0]

    assert session.verdict == TOO_FAST

    assert session.delta_sec == 340 - 380  # 40 s/km mais rápido que o piso


def test_tiro_nao_e_medido_por_media():
    # sessão estruturada (repeat) → STRUCTURED, fora do rate
    steps = [
        WorkoutStep(kind="run", distance_m=2000.0, pace_min="6:20"),
        WorkoutStep(
            kind="repeat",
            reps=3,
            steps=[WorkoutStep(kind="interval", duration_sec=60,
                               pace_min="5:35", pace_max="5:45")],
        ),
    ]

    report = _analyze(
        _plan([_session("Tuesday", "5:35", "5:45", steps=steps)]),
        [_run_at_pace("Tuesday", 500, 1)],  # média lenta, mas tem tiro
    )

    assert report.sessions[0].verdict == STRUCTURED

    # tiro sai da conta: sem sessão avaliável, rate é None
    assert report.rate is None


def test_tiro_detectado_pelo_nome_mesmo_sem_steps():
    # 'Intervalado VO2' sem passos estruturados: o nome basta pra não julgar
    # pela média (senão viraria falso 'pegou leve' — regra de ouro do Renato)
    session = _session("Tuesday", "5:30", "6:00")

    session.workout_type = "Intervalado VO2"

    report = _analyze(
        _plan([session]),
        [_run_at_pace("Tuesday", 394, 1)],  # média 6:34, lenta
    )

    assert report.sessions[0].verdict == STRUCTURED

    assert report.rate is None


def test_tempo_continuo_nao_e_tratado_como_tiro():
    # 'Tempo Run / Limiar' é esforço SUSTENTADO — a média vale, avalia normal
    session = _session("Tuesday", "5:50", "6:00")

    session.workout_type = "Tempo Run / Limiar"

    report = _analyze(
        _plan([session]),
        [_run_at_pace("Tuesday", 355, 1)],  # 5:55, dentro

    )

    assert report.sessions[0].verdict == ON_TARGET


def test_sessao_sem_alvo_de_pace_e_no_target():
    # plano externo sem pace (Mauricio) → não dá pra cobrar ritmo
    report = _analyze(
        _plan([_session("Tuesday", None, None)]),
        [_run_at_pace("Tuesday", 400, 1)],
    )

    assert report.sessions[0].verdict == NO_TARGET

    assert report.rate is None


def test_tolerancia_absorve_pequeno_desvio():
    # alvo 6:20–6:45; correu 6:03 (17 s/km abaixo do piso) → ainda ON_TARGET
    dentro = _analyze(
        _plan([_session("Tuesday", "6:20", "6:45")]),
        [_run_at_pace("Tuesday", 363, 1)],
    )

    assert dentro.sessions[0].verdict == ON_TARGET

    # 5:59 (21 s/km abaixo do piso) → passa da folga, vira TOO_FAST
    fora = _analyze(
        _plan([_session("Tuesday", "6:20", "6:45")]),
        [_run_at_pace("Tuesday", 359, 1)],
    )

    assert fora.sessions[0].verdict == TOO_FAST


def test_rate_mistura_avaliaveis_e_ignora_resto():
    # 3 avaliáveis (2 on, 1 slow) + 1 tiro + 1 sem alvo → rate = 2/3
    steps = [WorkoutStep(kind="repeat", reps=4,
                         steps=[WorkoutStep(kind="interval", duration_sec=60)])]

    plan = _plan([
        _session("Monday", "6:20", "6:45"),          # on
        _session("Tuesday", "6:20", "6:45"),         # on
        _session("Wednesday", "5:30", "5:45"),       # slow
        _session("Friday", "5:35", "5:45", steps=steps),  # tiro
        _session("Sunday", None, None),              # sem alvo
    ])

    activities = [
        _run_at_pace("Monday", 398, 1),
        _run_at_pace("Tuesday", 400, 2),
        _run_at_pace("Wednesday", 410, 3),
        _run_at_pace("Friday", 500, 4),
        _run_at_pace("Sunday", 400, 5),
    ]

    report = _analyze(plan, activities)

    assert len(report.on_target) == 2

    assert len(report.too_slow) == 1

    assert len(report.structured) == 1

    assert report.rate == round(2 / 3, 2) or abs(report.rate - 2 / 3) < 1e-9
