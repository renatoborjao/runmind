"""Aderência ao plano ao longo das semanas: série, tendência e — o que
importa de verdade — o dia/tipo que o atleta vive furando."""

from datetime import date, datetime, timedelta

from app.application.history.adherence_analyzer import AdherenceAnalyzer
from app.domain.entities.adherence_report import (
    ADHERENCE_FALLING,
    ADHERENCE_INSUFFICIENT,
    ADHERENCE_RISING,
    ADHERENCE_STABLE,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

# 4 semanas fechadas; a última é a de 20/07 (segunda)
LAST_WEEK = date(2026, 7, 20)

_DAY_OFFSET = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def _session(day, distance=6.0, workout_type="Rodagem", kind="run"):

    return PlannedSession(
        day=day,
        workout_type=workout_type,
        objective="",
        planned_distance_km=distance,
        planned_duration_minutes=None,
        target_pace_min=None,
        target_pace_max=None,
        kind=kind,
    )


def _plan(week_start, sessions):

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=20.0,
        running_days=[s.day for s in sessions],
        week_start=week_start,
        sessions=sessions,
    )


def _run(week_start, day, distance_km, activity_id):
    """Corrida real no dia da semana pedido, às 7h."""

    when = week_start + timedelta(days=_DAY_OFFSET[day])

    return make_activity(
        id=activity_id,
        start_date=datetime(when.year, when.month, when.day, 7, 0, 0),
        distance=distance_km * 1000,
    )


# "hoje" nos testes: domingo que fecha a última semana da série. Fixo de
# propósito — o analyzer ignora sessão que ainda não venceu, então um teste
# ancorado no relógio real mudaria de resultado conforme o dia da semana.
REFERENCE = LAST_WEEK + timedelta(days=6)


def _analyze(plans, activities, **kwargs):

    kwargs.setdefault("until_week", LAST_WEEK)

    return AdherenceAnalyzer.analyze(
        plans,
        TrainingHistory(activities),
        reference_date=REFERENCE,
        **kwargs,
    )


def _week_start(weeks_ago):

    return LAST_WEEK - timedelta(days=7 * weeks_ago)


def _plans_of(*sessions_per_week):
    """Um plano por semana, da mais ANTIGA pra mais recente."""

    total = len(sessions_per_week)

    return [
        _plan(_week_start(total - 1 - i), sessions)
        for i, sessions in enumerate(sessions_per_week)
    ]


def _standard_week():

    return [
        _session("Tuesday", 6.0),
        _session("Thursday", 5.0, "Intervalado"),
        _session("Saturday", 10.0, "Longão"),
    ]


def test_serie_conta_cumpridos_por_semana():

    plans = _plans_of(_standard_week(), _standard_week())

    activities = [
        # semana antiga: cumpriu as três
        _run(_week_start(1), "Tuesday", 6.0, 1),
        _run(_week_start(1), "Thursday", 5.0, 2),
        _run(_week_start(1), "Saturday", 10.0, 3),
        # semana recente: só a terça
        _run(LAST_WEEK, "Tuesday", 6.0, 4),
    ]

    report = _analyze(
        plans,
        activities,
        until_week=LAST_WEEK,
    )

    assert [(w.done, w.planned) for w in report.weeks] == [(3, 3), (1, 3)]

    assert report.weeks[0].week_start == _week_start(1)

    assert report.rate == round(4 / 6, 2)

    assert report.has_series


def test_dia_que_mais_escapa_vira_padrao():
    """Furou a quinta em 3 das 4 semanas — isso é padrão, e é a informação
    que permite ao coach mover o treino em vez de represcrever igual."""

    plans = _plans_of(*[_standard_week()] * 4)

    activities = []

    for i, week in enumerate([_week_start(3), _week_start(2),
                              _week_start(1), LAST_WEEK]):

        activities.append(_run(week, "Tuesday", 6.0, 10 * i + 1))

        activities.append(_run(week, "Saturday", 10.0, 10 * i + 2))

        # só na primeira semana ele fez a quinta
        if i == 0:

            activities.append(_run(week, "Thursday", 5.0, 10 * i + 3))

    report = _analyze(
        plans,
        activities,
        until_week=LAST_WEEK,
    )

    assert report.missed_day is not None

    assert report.missed_day.label == "Thursday"

    assert report.missed_day.count == 3

    assert report.missed_day.opportunities == 4

    # o tipo daquele dia acompanha (é o mesmo treino que escapa)
    assert report.missed_type is not None

    assert report.missed_type.label == "Intervalado"


def test_furo_isolado_nao_vira_padrao():
    """Uma quinta perdida numa semana de viagem não é padrão — afirmar isso
    seria acusar o atleta de algo que ele não faz."""

    plans = _plans_of(*[_standard_week()] * 4)

    activities = []

    for i, week in enumerate([_week_start(3), _week_start(2),
                              _week_start(1), LAST_WEEK]):

        activities.append(_run(week, "Tuesday", 6.0, 10 * i + 1))

        activities.append(_run(week, "Saturday", 10.0, 10 * i + 2))

        if i != 2:

            activities.append(_run(week, "Thursday", 5.0, 10 * i + 3))

    report = _analyze(
        plans,
        activities,
        until_week=LAST_WEEK,
    )

    assert report.missed_day is None

    assert report.missed_type is None


def test_padrao_exige_recorrencia_nao_so_repeticao():
    """Furar 2 de 8 quintas não é 'a quinta não acontece' — na maior parte
    das vezes acontece. Sem metade das oportunidades, não é padrão."""

    plans = _plans_of(*[_standard_week()] * 8)

    weeks = [_week_start(i) for i in range(7, -1, -1)]

    activities = []

    for i, week in enumerate(weeks):

        activities.append(_run(week, "Tuesday", 6.0, 100 * i + 1))

        activities.append(_run(week, "Saturday", 10.0, 100 * i + 2))

        if i >= 2:

            activities.append(_run(week, "Thursday", 5.0, 100 * i + 3))

    report = _analyze(
        plans,
        activities,
        until_week=LAST_WEEK,
    )

    assert len(report.weeks) == 8

    assert report.missed_day is None


def test_tendencia_caindo_e_subindo():

    plans = _plans_of(*[_standard_week()] * 4)

    weeks = [_week_start(3), _week_start(2), _week_start(1), LAST_WEEK]

    # duas semanas cheias, depois duas quase zeradas
    caindo = []

    for i, week in enumerate(weeks):

        caindo.append(_run(week, "Tuesday", 6.0, 10 * i + 1))

        if i < 2:

            caindo.append(_run(week, "Thursday", 5.0, 10 * i + 2))

            caindo.append(_run(week, "Saturday", 10.0, 10 * i + 3))

    report = _analyze(
        plans,
        caindo,
        until_week=LAST_WEEK,
    )

    assert report.trend == ADHERENCE_FALLING

    # o espelho: as mesmas semanas na ordem inversa = subindo
    subindo = []

    for i, week in enumerate(weeks):

        subindo.append(_run(week, "Tuesday", 6.0, 10 * i + 1))

        if i >= 2:

            subindo.append(_run(week, "Thursday", 5.0, 10 * i + 2))

            subindo.append(_run(week, "Saturday", 10.0, 10 * i + 3))

    report = _analyze(
        plans,
        subindo,
        until_week=LAST_WEEK,
    )

    assert report.trend == ADHERENCE_RISING


def test_tendencia_estavel_e_insuficiente():

    plans = _plans_of(*[_standard_week()] * 4)

    weeks = [_week_start(3), _week_start(2), _week_start(1), LAST_WEEK]

    activities = [
        _run(week, "Tuesday", 6.0, 10 * i + 1)
        for i, week in enumerate(weeks)
    ]

    report = _analyze(
        plans,
        activities,
        until_week=LAST_WEEK,
    )

    assert report.trend == ADHERENCE_STABLE

    # com 3 semanas a metade recente é uma só: qualquer viagem viraria
    # "caindo" — melhor não afirmar tendência
    curto = _analyze(
        _plans_of(*[_standard_week()] * 3),
        activities,
        until_week=LAST_WEEK,
    )

    assert curto.trend == ADHERENCE_INSUFFICIENT


def test_semana_regerada_conta_uma_vez_so():
    """Regerar o plano (force=True) acrescenta outra linha no histórico pra
    a MESMA semana; vale o último gravado, não as duas."""

    antigo = _plan(LAST_WEEK, [_session("Tuesday", 6.0)])

    novo = _plan(LAST_WEEK, _standard_week())

    report = _analyze(
        [antigo, novo],
        [_run(LAST_WEEK, "Tuesday", 6.0, 1)],
        until_week=LAST_WEEK,
    )

    assert len(report.weeks) == 1

    assert report.weeks[0].planned == 3


def test_janela_ignora_semanas_fora():

    plans = _plans_of(*[_standard_week()] * 4)

    report = _analyze(
        plans,
        [],
        until_week=LAST_WEEK,
        weeks=2,
    )

    assert [w.week_start for w in report.weeks] == [
        _week_start(1),
        LAST_WEEK,
    ]

    # semana futura (ainda não aconteceu) nunca entra
    futuro = _analyze(
        plans,
        [],
        until_week=_week_start(3),
    )

    assert [w.week_start for w in futuro.weeks] == [_week_start(3)]


def test_sem_plano_devolve_relatorio_vazio():

    report = _analyze(
        [],
        [],
        until_week=LAST_WEEK,
    )

    assert report.weeks == []

    assert report.rate is None

    assert report.trend == ADHERENCE_INSUFFICIENT

    assert not report.has_series


def test_semana_sem_sessao_de_corrida_e_ignorada():
    """Plano só de descanso/musculação não tem o que cobrar — entrar como
    0/0 sujaria a série e a taxa."""

    plans = [
        _plan(_week_start(1), [_session("Tuesday", None, "Força", "strength")]),
        _plan(LAST_WEEK, [_session("Tuesday", 6.0)]),
    ]

    report = _analyze(
        plans,
        [_run(LAST_WEEK, "Tuesday", 6.0, 1)],
        until_week=LAST_WEEK,
    )

    assert len(report.weeks) == 1

    assert report.rate == 1.0


def test_sessao_que_ainda_nao_venceu_nao_conta_como_furo():
    """Numa sexta-feira, o longão de domingo AINDA VAI acontecer — contá-lo
    como furado acusaria o atleta de algo que ele não fez (pego na validação
    com dado real: o domingo do Renato aparecia como perdido na sexta)."""

    sexta = LAST_WEEK + timedelta(days=4)

    report = AdherenceAnalyzer.analyze(
        _plans_of(_standard_week()),
        TrainingHistory([
            _run(LAST_WEEK, "Tuesday", 6.0, 1),
            _run(LAST_WEEK, "Thursday", 5.0, 2),
        ]),
        until_week=LAST_WEEK,
        reference_date=sexta,
    )

    assert report.weeks[0].planned == 2

    assert report.weeks[0].done == 2

    assert report.weeks[0].missed_days == []


def test_semana_inteira_no_futuro_nao_entra_na_serie():
    """Plano recém-gerado (semana que nem começou) não tem o que cobrar."""

    report = AdherenceAnalyzer.analyze(
        _plans_of(_standard_week()),
        TrainingHistory([]),
        until_week=LAST_WEEK,
        reference_date=LAST_WEEK - timedelta(days=1),
    )

    assert report.weeks == []
