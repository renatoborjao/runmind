"""ROTA ATÉ A META — a conta que faltava ao coach. Caso real (Leonardo, 21/10): 10 km em 1h em 8
semanas, longão parado em ~9 km, ~13 km por semana e 0% do tempo em zona forte; o coach via
tudo e dava o menor passo, semana após semana. Aqui o que a meta exige × pra onde o plano atual
leva, em números e em faixa (hipótese de treinador, nunca decreto)."""

from app.application.history.goal_path import (
    assess,
    goal_path_directive,
    goal_path_fact,
    reference_for,
)

# 8 semanas fechadas do Leonardo (da mais antiga pra mais recente): 4 anteriores, 4 recentes
_WEEKLY = [14.2, 5.1, 0.0, 13.3, 10.0, 12.6, 10.2, 22.1]
_LONGEST = [10.0, 5.1, 0.0, 8.3, 8.0, 7.5, 5.2, 9.0]


def _leonardo(**overrides):

    args = dict(
        distance_km=10.0, target_time="01:00:00", weeks_left=8,
        weekly_km=_WEEKLY, longest_km=_LONGEST, runs_per_week=3, hard_pct=0,
    )

    args.update(overrides)

    return assess(**args)


def test_the_reference_scales_with_the_distance():

    assert reference_for(5.0) == ((8, 10), (20, 30))
    assert reference_for(10.0) == ((11, 13), (28, 38))
    assert reference_for(15.0) == ((15, 18), (35, 45))
    assert reference_for(21.1) == ((18, 21), (40, 55))
    assert reference_for(42.2) == ((30, 35), (55, 75))


def test_leonardos_route_shows_what_the_plan_never_closes():
    """Longão parado (o maior recente, 9 km, abaixo dos 10 de antes) e volume subindo devagar: a
    diferença pra faixa de um 10 km em 1h aparece em km."""

    path = _leonardo()

    assert path is not None
    assert path.recent_long == 9.0 and path.best_long == 10.0
    # sem tendência de alta no longão: a projeção não passa do que ele já fez
    assert path.projected_long == 9.0
    assert round(path.long_gap) == 2
    # ~13,7 km/semana hoje, subindo ~0,7 por semana: chega com ~19 contra o piso de 28
    assert 18 < path.projected_week < 21
    assert 7 < path.week_gap < 10


def test_the_directive_names_the_gap_and_asks_to_close_it_starting_this_week():

    text = goal_path_directive(_leonardo())

    assert text.startswith("ROTA ATÉ A META")
    assert "faltam 8 semanas pra 10 km em 01:00:00" in text
    assert "~11-13 km" in text and "~28-38 km/semana" in text
    assert "maior treino recente 9 km" in text
    assert "FALTAM ~2 km no longão e ~9 km por semana" in text
    assert "o primeiro JÁ nesta semana" in text
    assert "proponha ajustar a meta" in text
    assert "Repetir a semana anterior sem dizer por quê é o único erro" in text
    # hipótese de treinador, não decreto
    assert "hipótese de treinador" in text and "não decreto" in text


def test_a_zero_hard_effort_athlete_is_pointed_to_a_capacity_test_but_the_choice_is_the_coachs():

    text = goal_path_directive(_leonardo(hard_pct=0))

    assert "capacidade real dele é desconhecida" in text
    assert "a decisão é sua" in text

    assert "capacidade real" not in goal_path_directive(_leonardo(hard_pct=12))


def test_the_fact_for_the_other_voices_has_no_dose_instruction():

    text = goal_path_fact(_leonardo())

    assert text.startswith("Rota até a meta (hipótese de treinador, não promessa)")
    assert "faltam ~2 km no longão e ~9 km por semana pra referência" in text
    assert "Se ele perguntar se está no caminho" in text
    assert "FALTAM" not in text and "primeiro JÁ" not in text


def test_a_path_that_already_covers_the_reference_says_so():

    weekly = [26.0, 28.0, 30.0, 29.0, 31.0, 32.0, 30.0, 33.0]

    longest = [11.0, 12.0, 12.0, 11.0, 12.0, 13.0, 12.0, 13.0]

    text = goal_path_directive(_leonardo(weekly_km=weekly, longest_km=longest, hard_pct=15))

    assert "a trajetória cobre a referência" in text
    assert "FALTAM" not in text


def test_with_more_runs_per_week_the_volume_reference_is_the_middle_of_the_range():

    three = _leonardo(runs_per_week=3)

    four = _leonardo(runs_per_week=4)

    # 3 corridas: piso (28); 4 corridas: meio da faixa (33) → a diferença de volume cresce
    assert four.week_gap - three.week_gap == 5


def test_no_route_without_a_dated_race_in_the_taper_or_without_runs():

    assert _leonardo(weeks_left=None) is None
    assert _leonardo(distance_km=None) is None
    # prova a menos de 3 semanas: o taper é quem manda
    assert _leonardo(weeks_left=2) is None
    # sem corrida recente não há o que projetar
    assert _leonardo(weekly_km=[0.0] * 8, longest_km=[0.0] * 8) is None

    assert goal_path_directive(None) == "" and goal_path_fact(None) == ""


def test_a_falling_recent_trend_is_not_projected_as_a_fall():
    """Queda recente (semana de gripe) não vira projeção de queda: a rota assume o que ele já
    sustenta, e só soma se houver tendência de alta."""

    path = _leonardo(weekly_km=[20.0, 22.0, 24.0, 22.0, 12.0, 10.0, 14.0, 12.0])

    assert path.projected_week == path.recent_week


def test_the_recent_pace_is_never_projected_far_above_his_best():
    """Maurício: 4 semanas subindo forte × 8 semanas de extrapolação dava ~69 km/semana. A projeção
    não passa de ~15% acima da melhor semana / do maior treino que ele já fez."""

    path = _leonardo(
        weekly_km=[10.0, 12.0, 11.0, 13.0, 30.0, 35.0, 40.0, 45.0],
        longest_km=[6.0, 7.0, 6.0, 7.0, 10.0, 12.0, 13.0, 15.0],
    )

    assert path.projected_week <= 45.0 * 1.15 + 0.01
    assert path.projected_long <= 15.0 * 1.15 + 0.01


def test_the_aim_follows_the_runs_per_week():

    assert "mire no piso" in goal_path_fact(_leonardo(runs_per_week=3))
    assert "mire no meio da faixa" in goal_path_fact(_leonardo(runs_per_week=4))
