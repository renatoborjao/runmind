"""A descarga é RESPOSTA do corpo, não calendário (Renato, 19/10: "a descarga só deve
acontecer se o atleta não estiver evoluindo ou sentindo a carga, ou na reta final da
prova; caso contrário, manter a evolução"). Só dispara com sinal: recuperação caindo
COM carga em alta, corpo sobrecarregado ou forma recuando com carga em alta."""

from app.application.history.deload_analyzer import (
    DeloadAnalyzer,
    deload_chat_line,
    deload_directive,
    race_owns_the_load,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    RISING,
    STABLE,
    RecoveryTrend,
)
from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_STABLE,
)


def _recovery(hrv=STABLE, rhr=STABLE) -> RecoveryTrend:

    return RecoveryTrend(
        hrv_direction=hrv,
        rhr_direction=rhr,
        days_covered=7,
    )


# ---- o calendário não dispara mais ------------------------------------------------


def test_weeks_of_rising_load_alone_never_bring_a_deload():
    """O 'clássico 3:1' saiu: 3, 4 ou 6 semanas subindo com o corpo firme seguem
    evoluindo — a contagem vira só informação."""

    for loads in ([80, 90, 100], [80, 90, 100, 110, 120, 130]):

        d = DeloadAnalyzer.assess(
            loads, _recovery(), acwr=1.2, body_state=BODY_ABSORBING,
        )

        assert d.due is False
        assert d.building_weeks == len(loads)
        assert deload_directive(d) == ""
        assert deload_chat_line(d) == ""


def test_elevated_load_alone_is_not_a_reason():
    """Carga em alta é o atleta SUBINDO — o que queremos. Fernanda 19/10: ACWR 1,43
    só porque veio de uma semana parada, HRV subindo."""

    d = DeloadAnalyzer.assess(
        [287, 185, 39, 284], _recovery(hrv=RISING), acwr=1.43,
        body_state=BODY_ABSORBING,
    )

    assert d.due is False


def test_recovery_week_resets_the_streak_count():

    d = DeloadAnalyzer.assess([100, 110, 50, 120], _recovery())

    assert d.building_weeks == 1
    assert d.due is False


def test_zeros_reset_streak():

    d = DeloadAnalyzer.assess([0, 0, 60, 70], _recovery())

    assert d.building_weeks == 2
    assert d.due is False


# ---- o corpo pede ------------------------------------------------------------------


def test_falling_recovery_with_elevated_load_brings_a_deload():

    d = DeloadAnalyzer.assess([90, 100], _recovery(hrv=FALLING), acwr=1.2)

    assert d.due is True
    assert "recuperação está caindo" in d.reason
    assert deload_directive(d).startswith("SINAL DE DESCARGA")
    assert "DECIDA" in deload_directive(d)
    assert "Não é calendário" in deload_directive(d)


def test_resting_heart_rate_worsening_counts_too():
    """rhr_direction é do ponto de vista da RECUPERAÇÃO: FALLING = piorando."""

    d = DeloadAnalyzer.assess([90, 100], _recovery(rhr=FALLING), acwr=1.1)

    assert d.due is True


def test_a_strained_body_brings_a_deload():

    d = DeloadAnalyzer.assess(
        [90, 100], _recovery(), acwr=1.4, body_state=BODY_STRAINED,
    )

    assert d.due is True
    assert "recuperação está caindo" in d.reason


def test_a_declining_form_with_elevated_load_brings_a_deload():

    d = DeloadAnalyzer.assess(
        [90, 100], _recovery(), acwr=1.15, form=EVO_DECLINING,
    )

    assert d.due is True
    assert "a forma recuou" in d.reason


def test_a_stalled_form_joins_the_reason_when_the_body_is_tired():
    """Parou de evoluir E o corpo está cansado: a razão fala das duas coisas."""

    d = DeloadAnalyzer.assess(
        [90, 100], _recovery(hrv=FALLING), acwr=1.2, form=EVO_STABLE,
    )

    assert d.due is True
    assert "parou de evoluir" in d.reason


def test_a_stalled_form_alone_is_not_a_deload():
    """Estagnar com o corpo fresco é falta de estímulo novo — descansar mais piora.
    A resposta é puxar (a diretriz de forma já pede isso), não aliviar."""

    d = DeloadAnalyzer.assess(
        [90, 100, 110], _recovery(), acwr=1.2, body_state=BODY_BALANCED,
        form=EVO_STABLE,
    )

    assert d.due is False


def test_an_improving_form_never_brings_one():

    d = DeloadAnalyzer.assess(
        [90, 100, 110], _recovery(), acwr=1.2, form=EVO_IMPROVING,
    )

    assert d.due is False


# ---- sem carga, nada pra aliviar -----------------------------------------------------


def test_low_acwr_blocks_deload_even_with_fatigue_signal():
    """Bug do Maurício: ACWR 0.97 (carga aguda <= crônica) + rhr caindo não
    justifica descarga — sem sobrecarga, semana leve à força só destreina."""

    d = DeloadAnalyzer.assess(
        [294, 151, 344, 252], _recovery(rhr=FALLING), acwr=0.97
    )

    assert d.due is False
    assert deload_directive(d) == ""


def test_a_declining_form_with_low_load_is_a_base_problem_not_a_deload():
    """Voltou de uma parada: a forma recuou porque destreinou, não porque cansou."""

    d = DeloadAnalyzer.assess(
        [0, 0, 120, 190], _recovery(), acwr=0.8, form=EVO_DECLINING,
    )

    assert d.due is False


def test_acwr_none_keeps_the_fatigue_signal_working():
    """Sem dado de ACWR, o sinal de recuperação ainda vale (retrocompat)."""

    d = DeloadAnalyzer.assess([80, 90, 100], _recovery(hrv=FALLING), acwr=None)

    assert d.due is True


# ---- a prova manda na carga ----------------------------------------------------------


def test_taper_zone_disables_deload():
    """Perto da prova o taper cuida do recuo — não empilha descarga."""

    d = DeloadAnalyzer.assess(
        [80, 90, 100, 110], _recovery(hrv=FALLING), acwr=1.3, weeks_to_race=2,
    )

    assert d.due is False
    assert "taper" in d.reason


def test_post_race_window_disables_deload():
    """Bug do Renato/Maurício: prova em 23/08 era o alvo, o coach afinou (cargas
    caíram no taper), a prova passou e voltamos a puxar. O histórico mostra
    'carga subindo' mas o recuo JÁ foi o taper+prova — não descarrega em cima,
    mesmo com ACWR inflado e recuperação caindo."""

    d = DeloadAnalyzer.assess(
        [341.8, 338.0, 652.6, 691.2],
        _recovery(hrv=FALLING),
        acwr=1.37,
        weeks_since_race=2,
    )

    assert d.due is False
    assert "pós-prova" in d.reason
    assert deload_directive(d) == ""


def test_deload_returns_after_post_race_window():
    """Passada a janela pós-prova, o corpo cansado volta a justificar a descarga."""

    d = DeloadAnalyzer.assess(
        [80, 90, 100, 110],
        _recovery(hrv=FALLING),
        acwr=1.3,
        weeks_since_race=5,
    )

    assert d.due is True


def test_race_owns_the_load_names_the_reason():

    assert race_owns_the_load(weeks_to_race=2) == "taper cuida do recuo"
    assert "pós-prova" in race_owns_the_load(weeks_since_race=1)
    assert race_owns_the_load(weeks_to_race=8, weeks_since_race=9) is None
    assert race_owns_the_load() is None
    # prova de treino não tem zona de taper
    assert race_owns_the_load(weeks_to_race=0, taper_zone_weeks=-1) is None
    # preparatória: mini-polimento de 1 semana
    assert race_owns_the_load(weeks_to_race=2, taper_zone_weeks=1) is None
    assert race_owns_the_load(weeks_to_race=1, taper_zone_weeks=1) is not None


# ---- recuperação caindo com carga BAIXA não é carga --------------------------------------


def test_recovery_flag_with_low_load_is_not_a_deload():
    """Recuperação caindo sem carga elevada é sono, vida ou doença — quem cuida é a
    leitura do corpo, não uma semana mais leve."""

    d = DeloadAnalyzer.assess(
        [300, 310], _recovery(hrv=FALLING), acwr=0.9,
        body_state=BODY_RECOVERY_FLAG,
    )

    assert d.due is False
