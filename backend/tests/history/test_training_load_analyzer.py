from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.history.training_load_analyzer import (
    TrainingLoadAnalyzer,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.hr_zones import HrZones
from app.domain.entities.training_load import (
    LOAD_DETRAINING,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_LIGHT,
    LOAD_OPTIMAL,
)

REF = date(2026, 7, 22)


def _act(days_ago: int, minutes: int, zones=None, bpm=None):
    """Atividade mínima: só o que o analisador usa (start_date + moving_time).
    `bpm` = treino inteiro nessa FC (vira HISTOGRAMA, o que a carga de Edwards
    usa); `zones` = minutos-por-zona GRAVADOS (a carga NÃO deve usar)."""

    day = REF - timedelta(days=days_ago)

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 10, 0),
        moving_time=minutes * 60,
        hr_zone_minutes=zones,
        hr_histogram={str(bpm): float(minutes)} if bpm else None,
        average_heartrate=None,
    )


# régua do renato2 (relógio, reserva de FC): Z1 128 · Z2 140 · Z3 152 · Z4 164 · Z5 176
RULER = HrZones(floors=(128, 140, 152, 164, 176), method="garmin:HR_RESERVE")


def _analyze(activities, zones=None):

    return TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=activities),
        reference_date=REF,
        zones=zones,
    )


def test_optimal_when_load_is_steady():

    # 60 min/dia por 28 dias -> aguda = crônica -> ACWR ~1.0
    load = _analyze([_act(d, 60) for d in range(28)])

    assert load.acute_load == 420.0
    assert load.chronic_load == 420.0
    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_high_when_ramping_fast():

    # base fraca + pico nos últimos 7 dias -> ACWR bem acima de 1.5
    acts = [_act(27, 30)] + [_act(d, 60) for d in range(7)]

    load = _analyze(acts)

    assert load.acwr > 1.5
    assert load.status == LOAD_HIGH


def test_one_light_week_is_light_not_detraining():

    # carregou 21 dias e parou SÓ na última semana -> aguda 0 -> ACWR 0, mas uma
    # semana leve é só uma semana leve (viagem, pausa médica, treino que mudou de
    # dia): estado próprio — nem "equilibrada" nem "queda de forma"
    load = _analyze([_act(d, 60) for d in range(7, 28)])

    assert load.acute_load == 0.0
    assert load.acwr == 0.0
    assert load.status == LOAD_LIGHT


def test_detraining_when_two_full_weeks_stay_below_usual():

    # 4 semanas de carga normal e depois as DUAS últimas semanas de calendário
    # (seg–dom) completas sem treinar -> queda que se sustenta = destreino
    load = _analyze([_act(d, 60) for d in range(17, 45)])

    assert load.acute_load == 0.0
    assert load.acwr == 0.0
    assert load.status == LOAD_DETRAINING


def test_current_partial_week_never_counts_as_light():

    # semanas completas normais (4 corridas de 60 min por semana) e a semana
    # em andamento com só 1 corrida: semana parcial não é queda
    acts = [_act(d, 60) for d in range(3, 60) if (REF - timedelta(days=d)).weekday() in (0, 2, 4, 5)]

    load = _analyze(acts)

    assert load.status != LOAD_DETRAINING


# ---------------- janela ancorada no último dia COMPLETO ----------------

_TODAY = date(2026, 9, 29)  # terça


def _run(day: date, minutes: int = 60):

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 7, 0),
        moving_time=minutes * 60,
        hr_zone_minutes=None,
        hr_histogram=None,
        average_heartrate=None,
    )


def _tue_thu_sat(first: date, last: date):
    """3x por semana (ter/qui/sáb), 60 min — a rotina do Renato."""

    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]

    return [_run(d) for d in days if d.weekday() in (1, 3, 5)]


def _as_of_today(monkeypatch, today: date):

    monkeypatch.setattr(
        "app.application.history.training_load_analyzer.today_local",
        lambda: today,
    )


def test_training_morning_before_the_run_is_not_a_drop(monkeypatch):

    # Renato 29/09, 7h da terça: a corrida de hoje ainda não aconteceu e a da
    # terça passada (22/09) já saiu da janela de 7 dias — a aguda ficava com 2
    # corridas de 3 e o ACWR ia a 0,73 ("destreino") com o volume de sempre
    _as_of_today(monkeypatch, _TODAY)

    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=_tue_thu_sat(date(2026, 8, 1), date(2026, 9, 26))),
        reference_date=_TODAY,
    )

    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_after_todays_run_the_day_counts(monkeypatch):

    _as_of_today(monkeypatch, _TODAY)

    acts = _tue_thu_sat(date(2026, 8, 1), date(2026, 9, 29))

    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts), reference_date=_TODAY
    )

    assert load.acwr == 1.0


def test_same_load_reads_the_same_before_and_after_the_run(monkeypatch):

    # manhã (sem a corrida de hoje) e noite (com ela) dizem a MESMA coisa
    _as_of_today(monkeypatch, _TODAY)

    before = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=_tue_thu_sat(date(2026, 8, 1), date(2026, 9, 26))),
        reference_date=_TODAY,
    )

    after = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=_tue_thu_sat(date(2026, 8, 1), date(2026, 9, 29))),
        reference_date=_TODAY,
    )

    assert before.acwr == after.acwr == 1.0


def test_last_complete_day_only_moves_today_without_a_session(monkeypatch):

    _as_of_today(monkeypatch, _TODAY)

    quiet = TrainingHistory(activities=[_run(date(2026, 9, 26))])
    ran = TrainingHistory(activities=[_run(_TODAY)])

    day = TrainingLoadAnalyzer._last_complete_day

    assert day(quiet, _TODAY) == date(2026, 9, 28)
    assert day(ran, _TODAY) == _TODAY
    # data de referência passada já é dia fechado: não anda
    assert day(quiet, date(2026, 9, 20)) == date(2026, 9, 20)


def test_insufficient_history_overrides_ratio():

    # só 5 dias de histórico: mesmo com ACWR alto, não arrisca veredito
    load = _analyze([_act(d, 60) for d in range(5)])

    assert load.days_of_history == 5
    assert load.status == LOAD_INSUFFICIENT


def test_weekly_loads_ordered_old_to_new():

    acts = [_act(0, 10), _act(7, 20), _act(14, 30), _act(21, 40)]

    load = _analyze(acts)

    assert load.weekly_loads == [40.0, 30.0, 20.0, 10.0]


def _hr_act(days_ago: int, minutes: int, hr):

    day = REF - timedelta(days=days_ago)

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 10, 0),
        moving_time=minutes * 60,
        average_heartrate=hr,
    )


# ---------------- v2: intensidade (duração × %FCR) ----------------


def test_intensity_weights_hard_sessions_more_than_easy():

    hard = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 160)]),
        reference_date=REF,
        resting_hr=60,
        max_hr=180,
    )

    easy = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 100)]),
        reference_date=REF,
        resting_hr=60,
        max_hr=180,
    )

    # mesma duração, FC maior -> mais carga
    assert hard.acute_load > easy.acute_load
    # hrr 160: (160-60)/(180-60)=0.833 -> 60*0.833 ~= 50
    assert hard.acute_load == 50.0


def test_without_hr_params_stays_duration_only():

    # sem FC repouso/máx: v1 (duração), ignora a FC da atividade
    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 160)]),
        reference_date=REF,
    )

    assert load.acute_load == 60.0


def test_session_without_hr_uses_median_factor():

    # 2 sessões com FC (fatores 1.0 e 0.0 -> mediana 0.5) + 1 sem FC de 100min
    acts = [
        _hr_act(0, 60, 180),   # hrr 1.0
        _hr_act(1, 60, 60),    # hrr 0.0
        _hr_act(2, 100, None),  # sem FC -> mediana 0.5 -> 50
    ]

    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts),
        reference_date=REF,
        resting_hr=60,
        max_hr=180,
    )

    # 60*1.0 + 60*0.0 + 100*0.5 = 110
    assert load.acute_load == 110.0


def test_banister_weights_hard_effort_more_than_linear():

    # com sexo, a exponencial de Banister pesa o esforço forte muito mais que
    # o %FCR linear (sem sexo)
    linear = TrainingLoadAnalyzer._intensity_factor(0.85, None)

    banister = TrainingLoadAnalyzer._intensity_factor(0.85, "M")

    assert linear == 0.85
    assert banister > linear


def test_banister_differs_by_sex():

    male = TrainingLoadAnalyzer._intensity_factor(0.8, "M")

    female = TrainingLoadAnalyzer._intensity_factor(0.8, "F")

    assert male != female


def test_sex_word_is_normalized():

    # onboarding pode gravar "masculino"/"feminino" — normaliza pela inicial
    assert (
        TrainingLoadAnalyzer._intensity_factor(0.7, "masculino")
        == TrainingLoadAnalyzer._intensity_factor(0.7, "M")
    )

    assert (
        TrainingLoadAnalyzer._intensity_factor(0.7, "feminino")
        == TrainingLoadAnalyzer._intensity_factor(0.7, "F")
    )


def test_invalid_max_hr_falls_back_to_duration():

    # FC máx <= repouso (dado torto): não pondera, cai na duração
    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 160)]),
        reference_date=REF,
        resting_hr=180,
        max_hr=170,
    )

    assert load.acute_load == 60.0


def test_empty_history_is_insufficient():

    load = _analyze([])

    assert load.acute_load == 0.0
    assert load.chronic_load == 0.0
    assert load.acwr is None
    assert load.status == LOAD_INSUFFICIENT
    assert load.days_of_history == 0
    assert load.weekly_loads == [0.0, 0.0, 0.0, 0.0]


# ------------------- carga de Edwards (por zonas) -------------------


def test_edwards_used_when_whole_window_has_histogram():
    """Toda atividade dos 28d tem histograma -> carga = Edwards (Σ min×peso)
    com as zonas relidas pela régua ATUAL. 60 min a 155 bpm = Z3 (×3) = 180."""

    load = _analyze([_act(d, 60, bpm=155) for d in range(28)], RULER)

    assert load.acute_load == 1260.0     # 7 dias × 180
    assert load.chronic_load == 1260.0
    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_edwards_weights_hard_sessions_more():
    """Mesma duração não distinguiria; Edwards sim: uma semana em Z5 pesa
    muito mais que a base em Z2 -> ACWR alto."""

    base = [_act(d, 60, bpm=145) for d in range(8, 28)]   # Z2
    peak = [_act(d, 60, bpm=180) for d in range(7)]       # Z5

    load = _analyze(base + peak, RULER)

    assert load.acwr > 1.5
    assert load.status == LOAD_HIGH


def test_falls_back_when_window_missing_histogram():
    """Uma atividade da janela SEM histograma -> não usa Edwards (não mistura
    unidade); cai no método por duração (aqui, sem FC = duração pura)."""

    acts = [_act(d, 60, bpm=155) for d in range(7)]
    # buraco na janela dos 28d, mas fora da janela aguda (7d)
    acts.append(_act(20, 60))

    load = _analyze(acts, RULER)

    # duração pura: 7 dias × 60 min na aguda -> 420 (não os valores de Edwards)
    assert load.acute_load == 420.0


def test_stored_zone_minutes_never_drive_load():
    """BUG da régua mista (renato2, 26/09): o mesmo esforço gravado com
    réguas diferentes (fórmula de idade → Z4; relógio → Z2) pesava até 35%
    menos depois da troca e o ACWR virava 'destreino' falso. A carga ignora
    os minutos-por-zona gravados e relê o histograma com UMA régua."""

    old_ruler = [_act(d, 60, zones=[0, 0, 0, 60, 0], bpm=150) for d in range(7, 28)]
    new_ruler = [_act(d, 60, zones=[0, 60, 0, 0, 0], bpm=150) for d in range(7)]

    load = _analyze(old_ruler + new_ruler, RULER)

    # mesma FC todo dia -> carga constante -> ACWR 1.0 (antes: 2/4 = 0.5)
    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_zone_minutes_without_histogram_fall_to_duration_not_edwards():
    """Atividades antigas (só minutos-por-zona gravados, sem histograma) não
    viram Edwards — a unidade seria da régua do dia da ingestão."""

    acts = [_act(d, 60, zones=[0, 0, 0, 0, 60]) for d in range(28)]

    load = _analyze(acts, RULER)

    assert load.acute_load == 420.0  # duração pura, não 7 × 300


# --- pós-prova: o taper não pode inflar o ACWR (bug do Renato) ---

def test_race_taper_does_not_inflate_acwr():
    """Prova em 23/08: taper (2 semanas de carga baixa) + reconstrução depois.
    Sem ciência de prova, o ACWR viraria ~1.4 (base deflacionada pelo taper).
    Com a prova, a base ignora as semanas baixas e usa as de carga REAL ->
    ACWR volta pro razoável e o status não é HIGH."""

    # semanas (antigo->novo): 2 normais, 2 de taper, 2 de reconstrução
    acts = []
    # 6-5 semanas atrás: carga normal (~600 min/sem = ~86/dia)
    for d in range(42, 28, -1):
        acts.append(_act(d, 86))
    # 4-3 semanas atrás: TAPER (carga baixa ~ metade)
    for d in range(28, 14, -1):
        acts.append(_act(d, 40))
    # 2-1 semanas atrás: reconstrução (carga normal de volta)
    for d in range(14, 0, -1):
        acts.append(_act(d, 86))

    race_day = REF - timedelta(days=15)  # dentro do taper/janela

    naive = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts), reference_date=REF,
    )
    aware = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts), reference_date=REF,
        recent_race_date=race_day,
    )

    # sem ciência de prova, o taper infla o ACWR bem acima do razoável
    assert naive.acwr > aware.acwr
    # com ciência, a base sobe (ignora o taper) e o ACWR fica perto de 1
    assert aware.acwr <= 1.2
    assert aware.status in (LOAD_OPTIMAL, LOAD_DETRAINING)


def test_no_race_uses_standard_four_weeks():
    """Sem prova, nada muda: a crônica segue as últimas 4 semanas normais."""

    acts = [_act(d, 60) for d in range(28)]

    with_flag = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts), reference_date=REF,
        recent_race_date=None,
    )

    assert with_flag.chronic_load == 420.0
    assert with_flag.acwr == 1.0


def test_race_outside_window_is_ignored():
    """Prova velha (fora dos 28d) não aciona o modo pós-prova."""

    acts = [_act(d, 60) for d in range(28)]

    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts), reference_date=REF,
        recent_race_date=REF - timedelta(days=60),
    )

    assert load.chronic_load == 420.0
    assert load.acwr == 1.0


def test_base_is_contiguous_block_before_taper_not_old_volume():
    """A base é o BLOCO contíguo antes do taper — não fura um gap de semanas
    baixas pra catar volume antigo lá de trás (ponto do Renato)."""

    acts = []
    # 9-10 sem atrás: volume ALTO e antigo (não deve entrar na base)
    for d in range(70, 56, -1):
        acts.append(_act(d, 90))
    # 6-8 sem atrás: GAP (quase parado)
    for d in range(56, 35, -1):
        acts.append(_act(d, 10))
    # 4-5 sem atrás: bloco real que levou à prova (a BASE certa)
    for d in range(35, 21, -1):
        acts.append(_act(d, 60))
    # 2-3 sem atrás: taper
    for d in range(21, 7, -1):
        acts.append(_act(d, 25))
    # última semana: reconstrução (não entra na base)
    for d in range(7, 0, -1):
        acts.append(_act(d, 60))

    race_day = REF - timedelta(days=10)

    aware = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts), reference_date=REF,
        recent_race_date=race_day,
    )

    # base ancora no bloco pré-taper (~420/sem), NÃO no volume antigo além do
    # gap (~630/sem) nem no taper (~175/sem)
    assert 380.0 <= aware.chronic_load <= 460.0


# ---- base baixa e semana parada (Leonardo/João 27/09) ----------------------


def test_a_week_off_does_not_turn_the_return_into_a_spike():
    """Leonardo: uma semana SEM treino no mês derrubava a base e a volta ao
    normal (o mesmo tempo de sempre) virava ACWR 1,62 — 'risco de lesão alto'."""

    # 3 semanas ativas; a de 7-13 dias atrás ficou PARADA
    acts = [_act(d, 40) for d in (1, 4, 15, 18, 22, 25)]

    load = _analyze(acts)

    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_low_base_needs_a_real_increase_of_time_to_be_a_spike():
    """João: ~40 min/semana; uma corrida um pouco maior não é 'sobrecarga'."""

    base = [_act(d, 35) for d in (9, 16, 23)]
    this_week = [_act(2, 55)]

    load = _analyze(base + this_week)

    assert load.acwr > 1.3
    assert load.status == LOAD_OPTIMAL
    assert load.low_base == (40, 15)


def test_beginner_big_jump_is_still_a_spike():
    """Base baixa, mas saltou de 40 pra 150 min: pico de verdade."""

    base = [_act(d, 40) for d in (9, 16, 23)]
    this_week = [_act(d, 50) for d in (1, 2, 3)]

    load = _analyze(base + this_week)

    assert load.status == LOAD_HIGH
    assert load.low_base is None
