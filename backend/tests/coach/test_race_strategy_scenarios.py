"""ESTRATÉGIA DE PROVA HONESTA (Renato, 20/10): planos A/B/C, passagens de controle e ajuste
de calor. Antes o cartão fechava sempre com "O ritmo está dentro do que você treinou —
confia no plano", mesmo quando não estava.

Caso real: Maurício, 15 km em 1:22:30 (5:30/km) com números entre ~1:24:27 (Garmin) e
~1:29:41 (seus treinos) — a meta está À FRENTE de tudo que ele já mostrou."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.application.coach.planning.race_strategy_engine import RaceStrategyEngine
from app.application.races.race_heat import (
    STRONG_HEAT_PCT,
    RaceHeat,
    _start_hour,
    heat_penalty_pct,
)
from app.application.races.race_strategy_service import RaceStrategyService
from app.domain.entities.training_goal import TrainingGoal
from app.infrastructure.integrations.weather.open_meteo_client import OpenMeteoClient

REPO = "app.infrastructure.persistence.nutrition_repository.NutritionRepository.load"

# 1:24:27 = 5067 s (Garmin) · 1:29:41 = 5381 s (treinos)
MAURICIO_PRED = {
    "seconds": 5381,
    "range": {"low_seconds": 5067, "high_seconds": 5381, "low_formatted": "1:24:27",
              "high_formatted": "1:29:41", "low_label": "Garmin", "high_label": "seus treinos"},
}


def _goal(km=15.0, target="01:22:30", race=date(2026, 12, 20)):

    return TrainingGoal(name="prova", distance_km=km, target_time=target, race_date=race)


def _plan(km=15.0, target="01:22:30"):

    return RaceStrategyEngine.plan(_goal(km, target))


def _secs(scenarios):

    return [round(s.total_minutes * 60) for s in scenarios.items]


# ---- onde a meta cai nos números ---------------------------------------------------------------


def test_a_target_ahead_of_every_number_starts_on_plan_b():
    """Maurício: 1:22:30 contra 1:24:27–1:29:41 → A é a meta, B o melhor dos números, C o
    pior; e o cartão diz pra largar no B."""

    sc = RaceStrategyEngine.scenarios(_plan(), MAURICIO_PRED)

    assert sc.position == "beyond"
    assert _secs(sc)[0] == 4950           # A = a meta (1:22:30)
    assert _secs(sc)[1] == 5067           # B = o melhor que os números sustentam
    assert _secs(sc)[2] == 5381           # C = o que os treinos já sustentaram
    assert [s.letter for s in sc.items] == ["A", "B", "C"]
    assert [s.role for s in sc.items] == ["ousado", "realista", "seguro"]
    assert [s.is_target for s in sc.items] == [True, False, False]
    assert sc.checkpoints == [5, 10]


def test_a_target_inside_the_range_is_plan_a_with_a_safety_net():

    sc = RaceStrategyEngine.scenarios(_plan(target="01:27:00"), MAURICIO_PRED)

    assert sc.position == "inside"
    assert _secs(sc)[0] == 5220
    assert _secs(sc)[0] < _secs(sc)[1] < _secs(sc)[2]
    assert sc.items[0].is_target


def test_a_target_slower_than_every_number_leaves_room_to_aim_higher():

    sc = RaceStrategyEngine.scenarios(_plan(target="01:35:00"), MAURICIO_PRED)

    assert sc.position == "beaten"
    assert _secs(sc)[0] == 5067          # A = o melhor dos números (mais rápido que a meta)
    assert _secs(sc)[1] == 5700          # B = a meta que o atleta definiu
    assert sc.items[1].is_target


def test_a_target_within_the_slack_of_the_fast_end_counts_as_inside():
    """João: Garmin 23:03 × meta 23:00 é empate técnico, não "à frente"."""

    pred = {"seconds": 1500, "range": {"low_seconds": 1383, "high_seconds": 1500}}

    sc = RaceStrategyEngine.scenarios(_plan(5.0, "00:23:00"), pred)

    assert sc.position == "inside"


def test_a_single_number_is_the_whole_evidence():

    pred = {"seconds": 5381}  # só o histórico

    ahead = RaceStrategyEngine.scenarios(_plan(), pred)
    inside = RaceStrategyEngine.scenarios(_plan(target="01:30:00"), pred)

    assert ahead.position == "beyond" and _secs(ahead)[1] == 5381
    assert inside.position == "beaten"


def test_without_a_prediction_nothing_is_claimed_about_the_athletes_numbers():
    """Sem previsão: A é a meta e B/C são só margem de dia — nenhuma afirmação."""

    sc = RaceStrategyEngine.scenarios(_plan(), None)

    assert sc.position is None
    assert _secs(sc) == [4950, 5024, 5100]    # +1,5% e +3% (C respeita a folga mínima do B)

    msg = RaceStrategyEngine.build("Mauricio", _goal())

    assert "Três planos pro dia" in msg
    assert "seus números" not in msg and "à frente do que" not in msg


def test_the_plans_are_always_ordered_and_apart():

    for target in ("01:22:30", "01:24:20", "01:27:00", "01:29:50", "01:40:00"):

        a, b, c = _secs(RaceStrategyEngine.scenarios(_plan(target=target), MAURICIO_PRED))

        assert a < b < c
        assert b >= a * 1.0099 and c >= b * 1.0149


def test_an_estimated_race_without_a_target_uses_the_evidence():

    goal = _goal(target=None)

    metrics = MagicMock(threshold_pace=5.5)

    plan = RaceStrategyEngine.plan(goal, metrics)

    sc = RaceStrategyEngine.scenarios(plan, MAURICIO_PRED)

    assert sc.position is None
    assert _secs(sc)[0] == 5067 and _secs(sc)[2] >= 5381
    assert not any(s.is_target for s in sc.items)


# ---- o cartão ----------------------------------------------------------------------------------


def _message(pred=MAURICIO_PRED, heat=None, target="01:22:30", km=15.0):

    with patch(REPO, return_value={"settings": {}}):

        return RaceStrategyEngine.build(
            "Mauricio", _goal(km, target), profile="mauricio", pred=pred, heat=heat,
        )


def test_the_card_tells_the_truth_when_the_target_is_ahead_of_the_numbers():

    msg = _message()

    assert "⚠️ Sua meta (1:22:30) está à frente do que seus números mostram hoje:" in msg
    assert "entre ~1:24:27 (Garmin) e ~1:29:41 (seus treinos)" in msg
    assert "largue no plano B e só vá pro A se a passagem do km 5 confirmar" in msg
    # a promessa velha, que não era verdade, saiu
    assert "dentro do que você treinou" not in msg
    assert "Largue no B, confie no que você treinou" in msg


def test_the_card_lists_the_three_plans_with_the_target_marked():

    msg = _message()

    assert "Três planos pro dia:" in msg
    assert "• A · ousado — 1:22:30 · 5:30/km ← sua meta" in msg
    assert "• B · realista — 1:24:27 · 5:38/km" in msg
    assert "• C · seguro — 1:29:41 · 5:59/km" in msg
    assert "🎯 Pace-alvo médio: *5:30/km*" in msg


def test_the_card_has_control_passages_at_the_thirds_with_a_decision_rule():

    msg = _message()

    assert "Passagens de controle (com a largada controlada):" in msg
    assert "• km 5: A 27:" in msg and "• km 10: A 55:" in msg
    assert " · B " in msg and " · C " in msg
    assert "mais rápido que o A → segura" in msg
    assert "atrás do C → pro C e termine bem" in msg


def test_a_10k_gets_a_single_checkpoint_and_a_short_race_none():

    assert "• km 5:" in _message(km=10.0, target="00:50:00", pred=None)

    short = _message(km=5.0, target="00:25:00", pred=None)

    assert "Passagens de controle" not in short
    assert "Passagem nos 2.5 km" in short


def test_the_inside_and_beaten_cases_read_differently():

    inside = _message(target="01:27:00")
    beaten = _message(target="01:35:00")

    assert "cabe na faixa dos seus números" in inside and "É o plano A" in inside
    assert "dá pra ir mais rápido que a sua meta (1:35:00)" in beaten
    assert "Escolha o plano pelo corpo na passagem" in inside


def test_the_nutrition_and_the_old_structure_are_still_there():

    msg = _message()

    assert "Largada CONTROLADA" in msg
    assert "Nutrição na prova (opcional)" in msg   # 82 min: 1 gel opcional


# ---- o calor -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "feels,expected",
    [(10, 0.0), (16, 0.0), (17, 1.0), (20, 1.0), (22, 2.5), (26, 4.5), (30, 7.0), (35, 9.0),
     (None, 0.0)],
)
def test_the_heat_table(feels, expected):

    assert heat_penalty_pct(feels) == expected


HEAT = {"temp": 25.6, "feels": 27.4, "humidity": 70, "hour": 7, "where": "São Paulo/SP",
        "penalty_pct": 4.5}


def test_the_card_adjusts_the_paces_to_the_forecast_heat():

    msg = _message(heat=HEAT)

    assert "🌡️ Previsão pro dia (São Paulo/SP, largada às 7h): ~26°C, sensação 27°C." in msg
    assert "O calor costuma custar ~4.5% do ritmo" in msg
    # A 5:30 × 1,045 = 5:45 · B 5:38 × 1,045 = 5:53 · C 5:59 × 1,045 = 6:15
    assert "use A 5:45 · B 5:53 · C 6:15 /km e hidrate mais cedo" in msg
    assert "Calor forte" not in msg


def test_a_strong_heat_adds_the_safety_message():

    msg = _message(heat={**HEAT, "feels": 33, "penalty_pct": 9.0})

    assert "Calor forte: priorize terminar bem — se passar mal, vá pro C." in msg
    assert 9.0 >= STRONG_HEAT_PCT


def test_a_cool_day_needs_no_adjustment_and_no_forecast_means_no_line():

    cool = _message(heat={**HEAT, "temp": 14, "feels": 13, "penalty_pct": 0.0})

    assert "sem ajuste de ritmo pelo clima" in cool

    assert "🌡️" not in _message(heat=None)


def test_the_region_label_when_the_race_city_is_unknown():

    msg = _message(heat={**HEAT, "where": "sua região"})

    assert "(sua região, largada às 7h)" in msg


# ---- a linha curta dos toques de prova ---------------------------------------------------------


def test_the_reminder_keeps_the_old_line_when_the_target_is_not_ahead():

    line = RaceStrategyEngine.reminder(_goal(target="01:27:00"), None, MAURICIO_PRED)

    assert line == "🎯 Lembrete: pace-alvo ~5:48/km, largada controlada."


def test_the_reminder_points_to_plan_b_when_the_target_is_ahead_of_the_numbers():

    line = RaceStrategyEngine.reminder(_goal(), None, MAURICIO_PRED)

    assert line == (
        "🎯 Lembrete: largada CONTROLADA — plano B ~5:38/km (A 5:30 só se confirmar, "
        "C 5:59). Decida na passagem do km 5."
    )


def test_the_reminder_mentions_the_heat_cost_in_seconds_per_km():

    line = RaceStrategyEngine.reminder(_goal(target="01:27:00"), None, MAURICIO_PRED, HEAT)

    assert "🌡️ Calor previsto (~26°C): o ritmo costuma pedir ~+16 s/km." in line


def test_the_reminder_without_a_way_to_estimate_is_none():

    assert RaceStrategyEngine.reminder(_goal(km=0.0), None) is None


# ---- previsão do tempo (Open-Meteo) ------------------------------------------------------------


def _response(payload):

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=payload)

    return response


def _patched_get(payload=None, error=None):

    async def fake_get(self, url, params=None):

        if error:

            raise error

        return _response(payload)

    return patch.object(httpx.AsyncClient, "get", fake_get)


def test_geocode_returns_the_first_match_and_uses_only_the_city():

    seen = {}

    async def fake_get(self, url, params=None):

        seen.update(params)

        return _response({"results": [{"latitude": -23.55, "longitude": -46.63}]})

    with patch.object(httpx.AsyncClient, "get", fake_get):

        coords = asyncio.run(OpenMeteoClient.geocode("São Paulo/SP"))

    assert coords == (-23.55, -46.63)
    assert seen["name"] == "São Paulo" and seen["countryCode"] == "BR"


def test_geocode_never_breaks():

    with _patched_get(error=httpx.ConnectError("sem rede")):

        assert asyncio.run(OpenMeteoClient.geocode("São Paulo/SP")) is None

    with _patched_get({"results": []}):

        assert asyncio.run(OpenMeteoClient.geocode("Lugar Nenhum")) is None

    assert asyncio.run(OpenMeteoClient.geocode("")) is None


def _hourly():

    times = [f"2026-12-20T{h:02d}:00" for h in range(24)]

    return {
        "hourly": {
            "time": times,
            "temperature_2m": [18 + (h / 2) for h in range(24)],
            "apparent_temperature": [19 + (h / 2) for h in range(24)],
            "relative_humidity_2m": [90 - h for h in range(24)],
        }
    }


def test_forecast_on_averages_the_hours_the_athlete_will_be_running():

    with _patched_get(_hourly()):

        forecast = asyncio.run(
            OpenMeteoClient.forecast_on(-23.5, -46.6, date(2026, 12, 20), 7, 2)
        )

    # 7h e 8h: temp 21.5 e 22 → 21.75; sensação 22.5 e 23 → 22.75; umidade 83 e 82
    assert forecast["temp"] == pytest.approx(21.75)
    assert forecast["feels"] == pytest.approx(22.75)
    assert forecast["humidity"] == pytest.approx(82.5)


def test_forecast_on_without_a_published_forecast_is_none():

    with _patched_get({"hourly": {"time": [], "temperature_2m": [],
                                  "apparent_temperature": [], "relative_humidity_2m": []}}):

        assert asyncio.run(OpenMeteoClient.forecast_on(-23.5, -46.6, date(2026, 12, 20))) is None

    with _patched_get(error=httpx.ReadTimeout("lento")):

        assert asyncio.run(OpenMeteoClient.forecast_on(-23.5, -46.6, date(2026, 12, 20))) is None


# ---- o serviço que junta tudo ------------------------------------------------------------------


def test_the_start_hour_comes_from_the_race_dossier():

    assert _start_hour({"start_time": "06:30"}) == 6
    assert _start_hour({"start_time": None}) == 7
    assert _start_hour({"start_time": "lixo"}) == 7
    assert _start_hour(None) == 7


def _runner():

    runner = MagicMock()
    runner.name = "Mauricio"

    return runner


def test_race_heat_only_looks_at_the_forecast_in_the_last_two_weeks():

    far = TrainingGoal(name="p", distance_km=15.0, target_time=None, race_date=date(2026, 12, 20))

    with patch("app.application.races.race_heat.today_local", return_value=date(2026, 10, 26)):

        assert asyncio.run(RaceHeat.for_race(_runner(), far, None, 82)) is None

    past = TrainingGoal(name="p", distance_km=15.0, target_time=None, race_date=date(2026, 10, 1))

    with patch("app.application.races.race_heat.today_local", return_value=date(2026, 10, 26)):

        assert asyncio.run(RaceHeat.for_race(_runner(), past, None, 82)) is None

    no_date = TrainingGoal(name="p", distance_km=15.0, target_time=None, race_date=None)

    assert asyncio.run(RaceHeat.for_race(_runner(), no_date, None, 82)) is None


def test_race_heat_uses_the_race_city_then_falls_back_to_where_the_athlete_runs():

    goal = TrainingGoal(name="p", distance_km=15.0, target_time=None, race_date=date(2026, 12, 20))

    forecast = {"temp": 25.0, "feels": 27.0, "humidity": 70.0}

    intel = {"city": "São Paulo/SP", "start_time": "07:30"}

    with (
        patch("app.application.races.race_heat.today_local", return_value=date(2026, 12, 12)),
        patch(
            "app.application.races.race_intel_service.RaceIntelService.for_runner",
            return_value=intel,
        ),
        patch.object(OpenMeteoClient, "geocode", AsyncMock(return_value=(-23.5, -46.6))),
        patch.object(OpenMeteoClient, "forecast_on", AsyncMock(return_value=forecast)) as fc,
    ):

        heat = asyncio.run(RaceHeat.for_race(_runner(), goal, None, 82))

    assert heat["where"] == "São Paulo/SP" and heat["hour"] == 7
    assert heat["penalty_pct"] == 4.5
    # 82 min de prova → janela de 2 h
    assert fc.await_args.kwargs == {"start_hour": 7, "hours": 2}

    # sem cidade no dossiê: a região onde ele corre
    with (
        patch("app.application.races.race_heat.today_local", return_value=date(2026, 12, 12)),
        patch(
            "app.application.races.race_intel_service.RaceIntelService.for_runner",
            return_value=None,
        ),
        patch(
            "app.application.planner.daily_training_notifier.DailyTrainingNotifier."
            "_latest_coords",
            return_value=(-23.6, -46.7),
        ),
        patch.object(OpenMeteoClient, "forecast_on", AsyncMock(return_value=forecast)),
    ):

        heat = asyncio.run(RaceHeat.for_race(_runner(), goal, MagicMock(), 82))

    assert heat["where"] == "sua região"


def test_race_heat_without_place_or_forecast_is_none():

    goal = TrainingGoal(name="p", distance_km=15.0, target_time=None, race_date=date(2026, 12, 20))

    with (
        patch("app.application.races.race_heat.today_local", return_value=date(2026, 12, 12)),
        patch(
            "app.application.races.race_intel_service.RaceIntelService.for_runner",
            return_value=None,
        ),
        patch(
            "app.application.planner.daily_training_notifier.DailyTrainingNotifier."
            "_latest_coords",
            return_value=None,
        ),
    ):

        assert asyncio.run(RaceHeat.for_race(_runner(), goal, MagicMock(), 82)) is None


def test_the_service_builds_the_card_with_the_prediction_and_the_heat():

    runner = _runner()

    history = MagicMock()

    with (
        patch(
            "app.application.races.race_strategy_service.RaceTimePredictor.predict_formatted",
            return_value=MAURICIO_PRED,
        ) as predict,
        patch(
            "app.application.races.race_strategy_service.RaceHeat.for_race",
            AsyncMock(return_value=HEAT),
        ),
        patch(REPO, return_value={"settings": {}}),
    ):

        card = asyncio.run(
            RaceStrategyService.message(runner, "mauricio", _goal(), None, history)
        )

    predict.assert_called_once_with(history, 15.0, "01:22:30", profile="mauricio")
    assert "à frente do que seus números mostram hoje" in card
    assert "🌡️ Previsão pro dia" in card


def test_a_failure_in_the_prediction_or_the_heat_never_breaks_the_card():

    with (
        patch(
            "app.application.races.race_strategy_service.RaceTimePredictor.predict_formatted",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "app.application.races.race_strategy_service.RaceHeat.for_race",
            AsyncMock(return_value=None),
        ),
        patch(REPO, return_value={"settings": {}}),
    ):

        card = asyncio.run(
            RaceStrategyService.message(_runner(), "mauricio", _goal(), None, MagicMock())
        )

    assert "Três planos pro dia" in card
    assert "à frente do que" not in card

    reminder = asyncio.run(
        RaceStrategyService.reminder(_runner(), "mauricio", _goal(km=0.0), None, None)
    )

    assert reminder is None


def test_the_chat_and_the_companion_use_the_service():
    """O atleta pede a estratégia no chat e os toques de prova leem a mesma fonte."""

    import inspect

    from app.application.coach.conversation import on_demand_answers
    from app.application.review import race_companion_notifier

    chat = inspect.getsource(on_demand_answers)
    companion = inspect.getsource(race_companion_notifier)

    assert "RaceStrategyService.message(" in chat
    assert "RaceStrategyService.reminder(" in companion
