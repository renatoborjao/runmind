"""FORTE PRESCRITO × FORTE ENTREGUE (nº 81). O coach prescrevia um forte em toda semana do
Leonardo e o sistema contava cada um como "feito" porque ele corria no dia — mas ele fazia
todos em ritmo de leve (ritmo de prova com alvo 6:00-6:15 saiu a 7:14; limiar 6:15-6:25 a
6:51; VO2 5:40-5:55 a 6:37, esforço 3/10). O aviso da auditoria dizia só "0% em zona forte",
sem semanas nem causa."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.history import stimulus_delivery as delivery
from app.application.history.stimulus_delivery import (
    DELIVERED,
    SOFT,
    UNKNOWN,
    assess,
    judge,
    render,
    weeks_since,
)
from app.application.monitoring import coach_sanity_audit as audit
from app.application.monitoring.coach_sanity_audit import (
    CoachSanityAudit,
    Finding,
    strong_not_delivered,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

TODAY = date(2026, 10, 29)    # quinta


def _session(day, workout_type, km=7.0):

    return PlannedSession(
        day=day, workout_type=workout_type, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
    )


def _plan(week_start, *sessions):

    return TrainingPlan(
        athlete_name="L", objective="10k", phase="BUILD", weekly_volume=20.0,
        running_days=[s.day for s in sessions], week_start=week_start, sessions=list(sessions),
    )


def _run(day: date, km: float, act_id: int):

    return make_activity(
        id=act_id, distance=km * 1000, moving_time=int(km * 400),
        start_date=datetime(day.year, day.month, day.day, 9, tzinfo=UTC),
    )


def _block(pace, target, ok, kind="run", m=3500):

    return {"kind": kind, "m": m, "pace": pace, "hr": 150, "target": target, "ok": ok}


def _rpe(day: date, value: int):

    return SimpleNamespace(day=day.isoformat(), rpe=value)


def _leonardo():
    """4 semanas de fortes feitos sem intensidade + 1 furado, como em 29/10."""

    plans = [
        _plan(date(2026, 10, 5), _session("Friday", "Ritmo de Prova", 8.0)),
        _plan(date(2026, 10, 12), _session("Sunday", "Limiar", 7.5)),
        _plan(date(2026, 10, 19), _session("Friday", "Velocidade / VO2", 7.1)),
        _plan(date(2026, 10, 26), _session("Monday", "Fartlek", 6.0)),
        _plan(date(2026, 9, 28), _session("Friday", "Tempo Run", 6.5)),
    ]

    runs = [
        _run(date(2026, 10, 9), 6.9, 1), _run(date(2026, 10, 18), 8.0, 2),
        _run(date(2026, 10, 23), 7.1, 3),
    ]

    log = {
        2: {"date": "2026-10-18", "km": 8.0, "blocks": [_block("6:53", "6:15-6:25", False)]},
    }

    rpes = [_rpe(date(2026, 10, 9), 3), _rpe(date(2026, 10, 18), 3), _rpe(date(2026, 10, 23), 3)]

    return plans, runs, log, rpes


# --- a sessão: entregou? ------------------------------------------------------------------------


def test_blocks_outside_the_target_band_are_a_soft_session_with_the_gap_in_seconds():

    entry = {"blocks": [_block("6:53", "6:15-6:25", False)]}

    item = judge(_session("Sunday", "Limiar"), None, entry, 3, date(2026, 10, 18))

    assert item.verdict == SOFT and item.gap_s == 28
    assert "0 de 1 blocos no ritmo-alvo, em média 28 s/km mais lento" in item.detail


def test_blocks_faster_than_the_band_are_delivered_not_soft():
    """Leonardo no fartlek de 02/10: 8 tiros a 5:17-5:48 com alvo 6:00-6:15 — passou do alvo, não
    ficou aquém. É pacing (rápido demais), não falta de estímulo."""

    blocks = [_block("5:30", "6:00-6:15", False, "interval", 250) for _ in range(8)]

    item = judge(_session("Friday", "Fartlek"), None, {"blocks": blocks}, 2, date(2026, 10, 2))

    assert item.verdict == DELIVERED
    assert "8 de 8 blocos no ritmo-alvo ou mais rápido (em média 30 s/km mais rápido" in item.detail
    # o quanto passou da faixa fica registrado (negativo): prova de que o alvo está abaixo dele
    assert item.gap_s == -30


def test_blocks_on_target_are_delivered_even_with_a_missed_rep():

    blocks = [_block("5:50", "5:40-5:55", True, "interval", 400) for _ in range(5)]

    blocks.append(_block("6:10", "5:40-5:55", False, "interval", 400))

    item = judge(_session("Friday", "Velocidade / VO2"), None, {"blocks": blocks}, 7, TODAY)

    assert item.verdict == DELIVERED and "5 de 6 blocos" in item.detail


def test_on_the_treadmill_the_watch_cannot_judge_so_it_is_not_a_soft_session():
    """Leonardo 09/10 (relógio descalibrado na esteira) e 23/10 (tiros a 5:27/km pelo painel, mais
    rápidos que o alvo de 5:40-5:55): o esforço de 3/10 do relógio não prova que foi leve."""

    act = _run(date(2026, 10, 23), 7.1, 9)

    act.raw["trainer"] = True

    item = judge(_session("Friday", "Velocidade / VO2"), act, None, 3, date(2026, 10, 23))

    assert item.verdict == UNKNOWN
    assert "esteira: o relógio não mede o ritmo" in item.detail

    # sem a marca de esteira, o mesmo esforço continua valendo como "de leve"
    outdoor = _run(date(2026, 10, 23), 7.1, 10)

    assert judge(_session("Friday", "Velocidade / VO2"), outdoor, None, 3, TODAY).verdict == SOFT


def test_another_recording_or_his_own_note_naming_the_treadmill_also_makes_it_unmeasured():
    """Leonardo 09/10: o treino principal foi gravado como corrida comum (6,9 km) e só uma 2ª
    gravação de 1,2 km se chamava "Corrida em esteira"; ele ainda escreveu "esteira" na nota."""

    plans = [_plan(date(2026, 10, 5), _session("Friday", "Ritmo de Prova", 8.0))]

    main = _run(date(2026, 10, 9), 6.9, 1)

    side = _run(date(2026, 10, 9), 1.2, 2)

    side.name = "Corrida em esteira"

    summary = assess(plans, [main, side], {}, [_rpe(date(2026, 10, 9), 3)], TODAY)

    assert summary.items[0].verdict == UNKNOWN and summary.soft == 0

    noted = SimpleNamespace(
        day="2026-10-09", rpe=3, note="corrida em esteira com diferença de calibração",
    )

    alone = assess(plans, [main], {}, [noted], TODAY)

    assert alone.items[0].verdict == UNKNOWN

    # sem nenhum sinal de esteira, o esforço de leve continua valendo
    assert assess(plans, [main], {}, [_rpe(date(2026, 10, 9), 3)], TODAY).items[0].verdict == SOFT


def test_without_measured_laps_how_he_felt_decides():

    session = _session("Friday", "Ritmo de Prova")

    soft = judge(session, None, None, 3, TODAY)
    hard = judge(session, None, None, 7, TODAY)
    unknown = judge(session, None, None, None, TODAY)

    assert soft.verdict == SOFT and "sentiu 3/10 (esforço de leve)" in soft.detail
    assert hard.verdict == DELIVERED
    assert unknown.verdict == UNKNOWN


# --- o resumo da janela --------------------------------------------------------------------------


def test_the_leonardo_case_prescribed_strong_every_week_and_delivered_none():

    plans, runs, log, rpes = _leonardo()

    summary = assess(plans, runs, log, rpes, TODAY)

    # 28/09 e 26/10 não têm corrida casada; só os dias já passados contam como prescritos
    assert summary.done == 3 and summary.delivered == 0 and summary.soft == 3
    assert summary.prescribed >= 4
    assert summary.last_delivered is None and summary.weeks_without is None
    assert summary.mean_rpe == 3.0
    assert summary.mean_gap_s == 28


def test_a_forte_delivered_three_weeks_ago_is_counted_in_weeks():

    plans, runs, log, rpes = _leonardo()

    log[3] = {"date": "2026-10-23", "km": 7.1, "blocks": [_block("5:50", "5:40-5:55", True)]}

    summary = assess(plans, runs, log, rpes, date(2026, 11, 13))

    assert summary.delivered == 1 and summary.last_delivered == date(2026, 10, 23)
    assert summary.weeks_without == 3 and weeks_since(summary, date(2026, 11, 13)) == 3


def test_no_forte_prescribed_means_no_summary():

    plans = [_plan(date(2026, 10, 5), _session("Monday", "Rodagem Leve", 5.0))]

    assert assess(plans, [_run(date(2026, 10, 5), 5.0, 1)], {}, [], TODAY) is None
    assert render(None) == ""
    assert weeks_since(None, TODAY) == delivery.WINDOW_WEEKS


def test_the_dossier_block_names_the_numbers_and_only_the_plan_voice_gets_the_cause_hint():

    plans, runs, log, rpes = _leonardo()

    summary = assess(plans, runs, log, rpes, TODAY)

    facts = render(summary)
    plan_voice = render(summary, directive=True)

    assert "FORTES: PRESCRITO × ENTREGUE" in facts
    assert "fazer o treino no dia certo não basta" in facts
    assert "entregues 0" in facts and "sem intensidade 3" in facts
    assert "Nenhum forte entregue nestas semanas" in facts
    assert "28 s/km mais lento que o alvo" in facts and "esforço percebido médio 3.0/10" in facts
    assert "- sex 09/10 Ritmo de Prova: sem intensidade" in facts

    assert "CONHECIMENTO" not in facts
    assert "mais um forte igual NÃO evolui" in plan_voice and "A decisão é sua" in plan_voice


# --- o aviso da auditoria -------------------------------------------------------------------------


def test_the_audit_says_how_long_and_why_instead_of_zero_percent_in_a_zone():

    plans, runs, log, rpes = _leonardo()

    found = strong_not_delivered("leonardo", assess(plans, runs, log, rpes, TODAY), TODAY)

    assert found.code == "forte_sem_intensidade" and found.level == audit.HIGH
    assert "Nas últimas 6 semanas nenhum treino forte bateu o alvo" in found.text
    assert "feitos 3, entregues 0, sem intensidade 3" in found.text
    assert "Ele corre o forte em ritmo de leve" in found.text and "tratar a causa" in found.text


def test_the_audit_stays_quiet_when_a_forte_was_delivered_recently_or_there_is_little_data():

    plans, runs, log, rpes = _leonardo()

    log[3] = {"date": "2026-10-23", "km": 7.1, "blocks": [_block("5:50", "5:40-5:55", True)]}

    assert strong_not_delivered("l", assess(plans, runs, log, rpes, TODAY), TODAY) is None
    assert strong_not_delivered("l", None, TODAY) is None

    few = assess(plans[:1], runs[:1], {}, rpes[:1], TODAY)

    assert strong_not_delivered("l", few, TODAY) is None


def test_the_audit_stays_high_when_the_last_delivered_forte_is_weeks_old():

    plans, runs, log, rpes = _leonardo()

    log[3] = {"date": "2026-10-23", "km": 7.1, "blocks": [_block("5:50", "5:40-5:55", True)]}

    summary = assess(plans, runs, log, rpes, date(2026, 11, 20))

    found = strong_not_delivered("leonardo", summary, date(2026, 11, 20))

    assert found is not None and found.level == audit.HIGH
    assert "Há 4 semanas sem um treino forte que bata o alvo (o último foi em 23/10)" in found.text


def test_the_vaguer_findings_do_not_repeat_when_the_forte_finding_explains_them():
    """Esforço baixo e "sem estímulo forte" ficam num aviso só: o novo diz a causa e as semanas."""

    data = SimpleNamespace(profile="leonardo", today=TODAY)

    effort = Finding("leonardo", "esforco_baixo", audit.WATCH, "vago")
    strong = Finding("leonardo", "forte_sem_intensidade", audit.HIGH, "preciso")

    patches = [
        patch(
            "app.application.coach.context.athlete_dossier.AthleteDossier._inputs",
            return_value=data,
        ),
        patch.object(CoachSanityAudit, "_check_race", return_value=None),
        patch.object(CoachSanityAudit, "_check_effort", return_value=effort),
        patch.object(CoachSanityAudit, "_check_asked_more", return_value=None),
        patch.object(CoachSanityAudit, "_check_path", return_value=None),
        patch.object(CoachSanityAudit, "_check_form", return_value=None),
        patch.object(CoachSanityAudit, "_check_easy_heavy", return_value=None),
        patch.object(CoachSanityAudit, "_check_no_quality", return_value=None),
        patch.object(CoachSanityAudit, "_check_stalled", return_value=None),
        patch.object(CoachSanityAudit, "_check_adherence", return_value=None),
        patch.object(CoachSanityAudit, "_check_stopped", return_value=None),
        patch.object(CoachSanityAudit, "_route_checks", return_value=[]),
        patch.object(CoachSanityAudit, "_check_delivery", return_value=strong),
    ]

    for p in patches:

        p.start()

    try:

        found = CoachSanityAudit.audit("leonardo", TODAY)

    finally:

        for p in patches:

            p.stop()

    assert [f.code for f in found] == ["forte_sem_intensidade"]


def test_the_plan_prompt_makes_the_coach_treat_the_cause_of_an_undelivered_forte():
    from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE

    flat = " ".join(PROMPT_TEMPLATE.split())

    assert 'FORTE ENTREGUE: o dossiê traz "FORTES: PRESCRITO × ENTREGUE"' in flat
    assert "mais um forte igual não evolui ninguém: trate a CAUSA" in flat
    assert "Prescrever e contar como feito não é estímulo" in flat
