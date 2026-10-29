"""A RÉGUA DE ESFORÇO DO ATLETA (nº 84). "Nem todos os atletas usam a medição de esforço certa"
(Renato, 29/10). Medido nos reais: Maurício responde 2 ou 3 em 22 de 23 corridas, mas o número
acompanha a FC (+0,74) e o ritmo (+0,83); Leonardo responde 3 em 73% das vezes e o número não
acompanha o ritmo (-0,03); Fernanda, 1 a 3 sem relação com a FC. O número só é evidência quando
acompanha o treino, e é lido pelo habitual DELE — nunca por um "≤3 é leve" de todos."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.history import effort_scale as es
from app.application.history.effort_scale import (
    FEW,
    FLAT,
    HIGH,
    LOW,
    READS,
    USUAL,
    EffortScale,
    build,
    describe,
    note,
    spearman,
)
from app.application.history.stimulus_delivery import DELIVERED, SOFT, UNKNOWN, judge
from app.application.history.stimulus_ledger import EASY
from app.application.history.training_patterns import TrainingPatterns
from app.application.monitoring.coach_sanity_audit import low_effort
from tests.coach.factories import make_activity

START = date(2026, 9, 1)


def _runs(n: int, hr_of, speed_of) -> list:
    """n corridas, uma por dia a partir de START, com FC e velocidade dadas por índice."""

    return [
        make_activity(
            id=i,
            start_date=datetime.combine(START + timedelta(days=i), datetime.min.time()),
            average_heartrate=hr_of(i),
            max_heartrate=190.0,
            average_speed=speed_of(i),
            distance=8000.0,
        )
        for i in range(n)
    ]


def _reports(values: list[int]) -> list:

    return [
        SimpleNamespace(day=(START + timedelta(days=i)).isoformat(), rpe=v)
        for i, v in enumerate(values)
    ]


# a intensidade sobe e desce em ciclos de 6 dias
def _hr(i):

    return 130.0 + (i % 6) * 8


def _speed(i):

    return 2.6 + (i % 6) * 0.18


# --- a correlação de postos -------------------------------------------------------------------


def test_spearman_handles_ties_and_flat_series():

    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert 0.5 < spearman([2, 2, 3, 3, 3, 4], [1, 2, 2, 3, 4, 4]) < 1.0
    # sem variação num dos lados não há correlação
    assert spearman([3, 3, 3, 3], [1, 2, 3, 4]) is None
    assert spearman([1, 2], [1, 2]) is None


# --- a régua: acompanha o treino? -------------------------------------------------------------


def test_the_compressed_rater_whose_number_follows_the_training_is_read_by_his_habit():
    """Maurício: só 2, 3 e 4 — mas 3 vem nos dias de FC e ritmo mais altos."""

    n = 24

    values = [2 if (i % 6) < 3 else 3 for i in range(n)]

    values[-1] = 4

    scale = build(_reports(values), _runs(n, _hr, _speed))

    assert scale.kind == READS and scale.reads and scale.rho > 0.7

    # o 2 é dos mais leves que ele relata; o 3 já é puxado pra ele; o 4, mais ainda
    assert scale.level(2) == LOW and scale.level(3) == HIGH and scale.level(4) == HIGH
    assert scale.high_from() == 3
    assert describe(3, scale) == "dos mais puxados que ele relata"


def test_the_flat_rater_who_answers_the_same_whatever_he_ran_is_not_evidence_of_anything():
    """Leonardo: 3 em quase tudo, sem relação com o ritmo nem com a FC."""

    n = 24

    values = [3] * n

    for i in (3, 11, 19):

        values[i] = 2

    values[7] = 4

    scale = build(_reports(values), _runs(n, _hr, _speed))

    assert scale.kind == FLAT and not scale.reads
    assert scale.level(3) is None and scale.level(2) is None
    assert describe(3, scale) == ""
    assert scale.below_habit([2, 2, 2, 2]) is False


def test_a_wide_scale_that_follows_the_training_is_read_against_his_own_habit():
    """Renato: 3 a 8, habitual 6-7."""

    n = 24

    values = [3 + (i % 6) for i in range(n)]

    scale = build(_reports(values), _runs(n, _hr, _speed))

    assert scale.reads and scale.level(3) == LOW and scale.level(8) == HIGH
    assert scale.level(5) == USUAL
    assert scale.below_habit([3, 3, 4]) is True
    assert scale.below_habit([5, 6, 5]) is False


def test_few_reports_or_no_matching_runs_cannot_prove_the_number_means_anything():

    assert build(_reports([3, 3, 3, 3, 3, 3, 3]), _runs(7, _hr, _speed)).kind == FEW
    assert build([], []).kind == FEW

    # relatos suficientes mas sem corrida casada no dia: não dá pra conferir
    far = _runs(24, _hr, _speed)

    for act in far:

        act.start_date = act.start_date + timedelta(days=400)

    assert build(_reports([2, 3] * 12), far).kind == FEW


def test_a_runner_without_a_heart_rate_watch_is_checked_against_his_pace():

    n = 24

    values = [3 + (i % 6) for i in range(n)]

    acts = _runs(n, lambda i: None, _speed)

    scale = build(_reports(values), acts)

    assert scale.reads


def test_the_scale_ignores_walks_and_other_sports():

    n = 24

    acts = _runs(n, _hr, _speed)

    for act in acts:

        act.sport = "Ride"

    assert build(_reports([3 + (i % 6) for i in range(n)]), acts).kind == FEW


# --- o que o coach lê -------------------------------------------------------------------------


def test_the_note_tells_how_to_read_each_kind_of_rater():

    n = 24

    compressed = build(
        _reports([2 if (i % 6) < 3 else 3 for i in range(n - 1)] + [4]), _runs(n, _hr, _speed),
    )

    assert "faixa estreita da escala (2 a 4, o habitual é 2.5)" in note(compressed)
    assert "3 ou mais é puxado pra ele" in note(compressed)

    flat = build(_reports([3] * n), _runs(n, _hr, _speed))

    text = note(flat)

    assert "NÃO acompanha o ritmo nem a FC" in text
    assert "100% das respostas são 3/10" in text
    assert "decida por ritmo, FC e blocos medidos" in text

    assert "poucos relatos (3)" in note(build(_reports([3, 3, 3]), []))
    assert note(build([], [])) == ""

    wide = build(_reports([3 + (i % 6) for i in range(n)]), _runs(n, _hr, _speed))

    assert "a escala dele vai de 3 a 8" in note(wide)
    assert "em relação ao habitual dele" in note(wide)


# --- quem usa a régua: forte entregue ----------------------------------------------------------


def _session(workout_type="Limiar"):

    return SimpleNamespace(workout_type=workout_type, day="Friday")


def test_a_flat_raters_number_never_makes_a_strong_session_soft_or_delivered():

    flat = EffortScale(reports=(3,) * 12, rho=0.0, pairs=12, kind=FLAT)

    for rpe in (2, 3, 7):

        item = judge(_session(), None, None, rpe, date(2026, 10, 23), scale=flat)

        assert item.verdict == UNKNOWN
        assert "o esforço que ele relata não separa leve de forte" in item.detail


def test_the_compressed_raters_relative_reading_decides_when_there_are_no_laps():

    compressed = EffortScale(
        reports=(2,) * 12 + (3,) * 10 + (4,), rho=0.8, pairs=23, kind=READS,
    )

    low = judge(_session(), None, None, 2, date(2026, 10, 23), scale=compressed)
    high = judge(_session(), None, None, 3, date(2026, 10, 23), scale=compressed)

    assert low.verdict == SOFT and high.verdict == DELIVERED


def test_measured_laps_still_decide_whatever_the_scale_says():

    block = {"kind": "run", "ok": True, "pace": "6:10", "target": "6:00-6:15"}

    flat = EffortScale(reports=(3,) * 12, rho=0.0, pairs=12, kind=FLAT)

    item = judge(_session(), None, {"blocks": [block]}, 3, date(2026, 10, 23), scale=flat)

    assert item.verdict == DELIVERED


# --- quem usa a régua: leve sentido pesado ---------------------------------------------------


def test_an_easy_run_felt_heavy_needs_a_number_that_means_something_and_is_high_for_him():

    day = date(2026, 10, 20)

    sessions = [(day, SimpleNamespace(workout_type="Rodagem"), EASY, None)]

    rpes = _reports([3 + (i % 6) for i in range(23)])

    rpes.append(SimpleNamespace(day=day.isoformat(), rpe=8))

    runs = _runs(24, _hr, _speed)

    # escala que acompanha: 8 é dos mais puxados dele → "leve sentido pesado"
    lines = TrainingPatterns._rpe_lines(sessions, rpes, runs)

    assert lines and "20/10 (8/10)" in lines[0]

    # quem usa a faixa 2-4 e sobe o número quando corre mais forte: 3 é puxado pra ele, mas não é
    # "leve sentido pesado" (não é pesado em absoluto)
    narrow = _reports([2 if (i % 6) < 3 else 3 for i in range(24)])

    narrow[-1] = SimpleNamespace(day=day.isoformat(), rpe=4)

    assert TrainingPatterns._rpe_lines(sessions, narrow, runs) == []

    # número que não acompanha o treino: o mesmo 8 não prova fadiga
    flat = _reports([3] * 23)

    flat.append(SimpleNamespace(day=day.isoformat(), rpe=8))

    assert TrainingPatterns._rpe_lines(sessions, flat, runs) == []


# --- e a auditoria: o caso Leonardo e o caso Maurício --------------------------------------


def test_the_audit_does_not_accuse_low_effort_of_a_habitual_low_rater():

    n = 24

    values = [2 if (i % 6) < 3 else 3 for i in range(n)]

    scale = build(_reports(values), _runs(n, _hr, _speed))

    assert scale.reads

    # últimas corridas: 2-3 como sempre → é o habitual dele, não esforço baixo
    assert low_effort("m", values[-6:], 0, 8, "01:00:00", "a prova", scale) is None


def test_constants_make_sense():

    assert es.MIN_REPORTS >= 8 and es.LOW_RANK < es.HIGH_RANK
