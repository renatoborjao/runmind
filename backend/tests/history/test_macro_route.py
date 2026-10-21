"""ROTA SEMANA A SEMANA (nº 80). O plano estagnava (mesmo longão, mesma dose, o forte só trocando de
nome) ou oscilava em dente de serra (Leonardo: 8 → 22 → 6 km) porque o coach montava UMA semana
por vez, ancorado na anterior. A rota é a curva que faltava: parte do que o atleta FEZ, sobe
enquanto ele cumpre, planeja simulado e polimento e gira o foco do estímulo. É guia, não trilho."""

from datetime import date

from app.application.coach.planning.race_map import (
    BASE,
    BUILD,
    RECOVERY,
    SIMULATED,
    SPECIFIC,
    TAPER,
    RaceMapBuilder,
)
from app.application.history import macro_route
from app.application.history.macro_route import baseline_km, build, render, snapshot, week_for

REF = date(2026, 10, 26)      # segunda

RACE = date(2026, 12, 20)


def _phases(race=RACE, distance=10.0, ref=REF):

    race_map = RaceMapBuilder.build(race, distance, ref)

    return [seg.key for seg in race_map.segments for _ in range(seg.weeks)]


def _leonardo(**over):

    args = dict(
        ref_week=REF, phases=_phases(), distance_km=10.0, target_time="01:00:00", race_date=RACE,
        executed_weeks=[0, 13.3, 10.0, 12.6, 10.2, 22.1, 8.0],
        longest_runs=[0, 8.3, 10.0, 7.5, 5.2, 9.0, 8.0], quality_done_km=8.0, runs_per_week=3,
        slack=True,
    )

    args.update(over)

    return build(**args)


# --- o ponto de partida é o FEITO ----------------------------------------------------------------


def test_the_baseline_is_what_he_sustains_not_his_one_best_week():
    """Leonardo fez 22,1 km UMA vez (4 corridas). A semana boa isolada não vira o chão: vale a
    mediana das últimas ou 90% da segunda melhor."""

    value, basis = baseline_km([0, 13.3, 10.0, 12.6, 10.2, 22.1, 8.0])

    assert 11 < value < 13
    assert "segunda melhor" in basis


def test_no_runs_no_route():

    assert baseline_km([0, 0, 0]) is None
    assert _leonardo(executed_weeks=[0, 0], longest_runs=[0, 0]) is None


def test_the_route_starts_from_what_he_did_and_rises_with_him():

    route = _leonardo()

    first = route.weeks[0]

    # a 1ª semana é um passo sobre o feito (~12 km), não o salto do papel (22 km)
    assert 12 <= first.volume_km <= 14
    assert route.growth_pct <= 10.01

    build_weeks = [w for w in route.weeks if w.phase == BUILD]

    volumes = [w.volume_km for w in build_weeks]

    # sobe toda semana (nenhum recuo por calendário) e o longão sobe junto
    assert volumes == sorted(volumes) and volumes[-1] > volumes[0] * 1.2
    assert [w.long_km for w in build_weeks] == sorted(w.long_km for w in build_weeks)
    assert build_weeks[-1].quality_km > build_weeks[0].quality_km


def test_with_room_to_spare_the_route_may_climb_faster_than_without():

    with_slack = _leonardo(slack=True)
    without = _leonardo(slack=False)

    assert with_slack.peak_km > without.peak_km
    assert without.growth_pct <= 7.01


def test_an_athlete_already_above_the_reference_holds_instead_of_climbing():
    """Maurício corre mais que a referência da distância: a rota segura o volume e evolui a
    qualidade, não empurra volume à toa."""

    route = build(
        ref_week=REF, phases=_phases(distance=15.0), distance_km=15.0, target_time="01:15:00",
        race_date=RACE, executed_weeks=[43, 45, 44, 43], longest_runs=[19, 20, 19, 20],
        quality_done_km=9.0, runs_per_week=5, slack=True,
    )

    assert route.growth_pct < 1.0
    assert route.peak_km < 50


# --- fases, simulado e polimento -----------------------------------------------------------------


def test_the_route_plans_the_taper_and_the_simulation_without_a_calendar_deload():

    route = _leonardo()

    phases = [w.phase for w in route.weeks]

    assert phases[-1] == TAPER and SIMULATED in phases and SPECIFIC in phases

    simulated = next(w for w in route.weeks if w.phase == SIMULATED)

    race_week = route.weeks[-1]

    # simulado: o longão vira o teste no ritmo de prova, mais curto que o pico
    assert simulated.long_km <= 0.8 * 10.0 + 0.01
    assert simulated.volume_km < max(w.volume_km for w in route.weeks)
    # a semana da prova tem a prova + um trote, e a prova é o longão
    assert race_week.volume_km >= 10.0 + 4.0
    assert race_week.long_km == 0 and "prova" in race_week.note

    # nas semanas de construção/ritmo nenhuma é menor que a anterior
    ramp = [w.volume_km for w in route.weeks if w.phase in (BASE, BUILD, SPECIFIC)]

    assert ramp == sorted(ramp)


def test_a_half_marathon_gets_a_longer_taper():

    route = build(
        ref_week=REF, phases=_phases(date(2027, 4, 4), 21.0975), distance_km=21.0975,
        target_time="02:00:00", race_date=date(2027, 4, 4), executed_weeks=[28, 31, 29, 18, 31, 30],
        longest_runs=[14, 15, 14, 10, 15, 16], quality_done_km=10, runs_per_week=3,
    )

    taper = [w for w in route.weeks if w.phase == TAPER]

    assert len(taper) == 2 and taper[0].volume_km > taper[1].volume_km
    assert route.weeks[-1].volume_km >= 21.0975 + 4.0


def test_a_preparatory_race_gets_a_mini_taper_and_a_lighter_recovery_week():

    race_map = RaceMapBuilder.build(
        RACE, 21.0975, REF, waypoints=[{"date": date(2026, 11, 22), "label": "15 km"}],
    )

    phases = [seg.key for seg in race_map.segments for _ in range(seg.weeks)]

    route = build(
        ref_week=REF, phases=phases, distance_km=21.0975, target_time="02:00:00", race_date=RACE,
        executed_weeks=[28, 30, 29, 31], longest_runs=[14, 15, 14, 16], quality_done_km=10,
    )

    mini = next(w for w in route.weeks if w.phase == "mini_polimento")

    after = route.weeks[route.weeks.index(mini) + 1]

    assert after.phase == RECOVERY
    assert mini.volume_km < route.weeks[route.weeks.index(mini) - 1].volume_km
    assert "preparatória" in mini.note and "depois da prova" in after.note


def test_without_a_dated_race_the_route_rolls_for_eight_weeks_without_a_taper():

    route = build(
        ref_week=REF, phases=None, distance_km=None, target_time=None, race_date=None,
        executed_weeks=[20, 22, 21, 23], longest_runs=[9, 10, 10, 11],
    )

    assert route.rolling and len(route.weeks) == 8
    assert all(w.phase == BUILD for w in route.weeks)
    # sem meta de distância o teto é o que ele já sustenta + ~35%
    assert route.peak_km <= 22 * 1.35 + 1


def test_coming_back_from_a_layoff_starts_light():

    normal = _leonardo()

    back = _leonardo(layoff_days=21)

    assert back.weeks[0].volume_km < 0.7 * normal.weeks[0].volume_km
    assert back.weeks[1].volume_km < normal.weeks[1].volume_km
    assert "retomada" in back.weeks[0].note
    # a terceira semana já é a da rota normal
    assert abs(back.weeks[2].volume_km - normal.weeks[2].volume_km) < 0.01


# --- variação ------------------------------------------------------------------------------------


def test_the_suggested_focus_rotates_so_the_same_stimulus_is_not_repeated():

    route = _leonardo()

    focus = [w.focus.split(";")[0] for w in route.weeks if w.phase == BUILD]

    assert len(set(focus)) == len(focus) >= 4
    assert "limiar" in focus[0] and "VO2" in focus[1]

    # o longão também muda de forma
    long_forms = {w.focus.split("longão: ")[1] for w in route.weeks if "longão: " in w.focus}

    assert len(long_forms) >= 3


def test_race_pace_work_grows_toward_the_race_phase():

    route = _leonardo()

    specific = [w.specific_km for w in route.weeks if w.phase in (BUILD, SPECIFIC)]

    assert specific == sorted(specific) and specific[-1] > specific[0] * 2


# --- o que o plano guarda e o que o coach lê -----------------------------------------------------


def test_the_snapshot_keeps_the_next_weeks_with_the_band_the_ledger_reads_back():

    route = _leonardo()

    saved = snapshot(route)

    assert len(saved["weeks"]) == 4 and saved["weeks"][0]["w"] == "2026-10-26"
    lo, hi = saved["weeks"][0]["km"]

    assert lo < saved["weeks"][0]["vol"] < hi
    assert snapshot(None) is None
    assert week_for(route, date(2026, 11, 2)).index == 2
    assert week_for(route, date(2030, 1, 1)) is None


def test_the_plan_voice_gets_the_route_as_a_guide_with_the_motive_rule():

    text = render(_leonardo())

    assert "NÃO trilho" in text and "o que ele FEZ" in text
    assert text.count("- sem ") == 4 and "- Depois:" in text
    assert "foco sugerido" in text
    # o desvio exige MOTIVO, o recuo só pelo corpo, e repetir não é prudência
    assert '"route_note"' in text and "±20%" in text
    assert "nunca por calendário" in text and "repetir a semana anterior" in text


def test_the_other_voices_get_only_the_facts():

    text = render(_leonardo(), directive=False)

    assert text.count("- sem ") == 2
    assert "COMO USAR" not in text and "Depois:" not in text


def test_the_rolling_route_says_so():

    route = build(
        ref_week=REF, phases=None, distance_km=None, target_time=None, race_date=None,
        executed_weeks=[20, 22, 21, 23], longest_runs=[9, 10, 10, 11],
    )

    assert "rolante, sem prova com data" in render(route)
    assert render(None) == ""


def test_the_module_keeps_the_numbers_as_documented_constants():

    assert macro_route.BAND == 0.10 and macro_route.ROLLING_WEEKS == 8
