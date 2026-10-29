"""CALIBRAÇÃO DO PACE PELA EVOLUÇÃO (nº 83). O VDOT do Leonardo vinha de um 10 km submáximo (1:07
com FC de leve): limiar 6:16, VO2 5:46 — enquanto o relógio projeta 56:33, os tiros saem 28
s/km mais rápido que o alvo e ele diz que as metas estão baixas. O modelo só subia com uma
prova: o coach "braço de ferro" que segura o atleta que já evoluiu. Aqui o VDOT acompanha a
evidência OBJETIVA (ele passa da faixa do plano nos fortes) até uma fração do que o relógio
projeta."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.application.history import pace_calibration as pc
from app.application.history.pace_calibration import (
    Calibration,
    calibrate,
    garmin_vdot,
    note,
    slack_sessions,
)
from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.history.stimulus_delivery import DELIVERED, SOFT, Delivery
from app.domain.entities.race_prediction import RacePrediction
from app.domain.entities.training_history import TrainingHistory
from tests.history.test_pace_model_builder import _pace_str, _run

TODAY = date(2026, 10, 29)

# Leonardo: o relógio projeta 5 km em 27:21 e 10 km em 56:33
GARMIN = RacePrediction(time_5k_sec=27 * 60 + 21, time_10k_sec=56 * 60 + 33)

BASE_VDOT = 30.9


def _faster(day: date, gap: int = -28, rpe: int | None = 2) -> Delivery:
    """Um forte feito MAIS RÁPIDO que a faixa (gap negativo = quanto passou)."""

    return Delivery(day, "Fartlek", DELIVERED, "x", gap, rpe)


def _two() -> list[Delivery]:

    return [_faster(date(2026, 10, 2)), _faster(date(2026, 10, 23), -13, 3)]


# --- o VDOT do relógio ---------------------------------------------------------------------------


def test_the_watch_vdot_is_the_average_of_the_5k_and_10k_it_projects():

    value = garmin_vdot(GARMIN)

    assert 34 < value < 36
    assert garmin_vdot(None) is None
    assert garmin_vdot(RacePrediction()) is None
    # só uma distância já serve
    assert garmin_vdot(RacePrediction(time_10k_sec=3393)) > 34


# --- a evidência: passar da faixa, não o que ele diz sentir --------------------------------------


def test_only_sessions_clearly_faster_than_the_band_count_and_not_just_feeling_easy():
    """Maurício dá ≤3/10 em 21 de 22 corridas por hábito: o esforço sozinho não move o pace."""

    items = [
        _faster(date(2026, 10, 2)),
        Delivery(date(2026, 10, 9), "Limiar", DELIVERED, "x", 0, 2),         # na faixa, esforço 2
        Delivery(date(2026, 10, 12), "Limiar", DELIVERED, "x", -3, 2),       # passou por nada
        Delivery(date(2026, 10, 16), "Limiar", SOFT, "x", 28, 2),            # ficou aquém
        Delivery(date(2026, 10, 20), "VO2", DELIVERED, "x", -20, 8),         # se matou pra isso
        Delivery(date(2026, 8, 20), "Fartlek", DELIVERED, "x", -30, 2),      # velho demais
        Delivery(date(2026, 10, 23), "VO2", DELIVERED, "x", -13, None),      # sem esforço relatado
    ]

    assert slack_sessions(items, TODAY) == 2


# --- a calibração --------------------------------------------------------------------------------


def test_the_leonardo_case_moves_half_the_way_to_the_watch_with_two_sessions():

    result = calibrate(BASE_VDOT, GARMIN, _two(), TODAY)

    assert result.sessions == 2 and result.weight == 0.5
    assert BASE_VDOT < result.vdot < result.garmin_vdot
    assert round(result.vdot, 1) == round(BASE_VDOT + 0.5 * (result.garmin_vdot - BASE_VDOT), 1)


def test_more_confirming_sessions_pull_further_but_never_past_the_optimistic_watch():

    three = _two() + [_faster(date(2026, 10, 26), -15, 3)]

    many = _two() + [_faster(date(2026, 10, 20 + i % 6), -15, 3) for i in range(12)]

    assert calibrate(BASE_VDOT, GARMIN, three, TODAY).weight == 0.6
    assert calibrate(BASE_VDOT, GARMIN, many, TODAY).weight == 0.9

    top = calibrate(BASE_VDOT, GARMIN, many, TODAY)

    assert top.vdot < top.garmin_vdot


def test_nothing_changes_without_the_watch_without_a_gap_without_evidence_or_after_a_race():

    assert calibrate(BASE_VDOT, None, _two(), TODAY) is None
    # relógio a menos de 4% do histórico = sem o que calibrar
    assert calibrate(34.0, GARMIN, _two(), TODAY) is None
    # uma sessão só não basta
    assert calibrate(BASE_VDOT, GARMIN, _two()[:1], TODAY) is None
    assert calibrate(BASE_VDOT, GARMIN, [], TODAY) is None
    assert calibrate(None, GARMIN, _two(), TODAY) is None
    # uma prova recente já ancora o VDOT em esforço máximo
    assert calibrate(BASE_VDOT, GARMIN, _two(), TODAY, recent_race=True) is None


def test_the_note_explains_where_the_paces_came_from():

    text = note(calibrate(BASE_VDOT, GARMIN, _two(), TODAY))

    assert "Ritmos CALIBRADOS pela evolução dele" in text
    assert "o histórico sozinho dava VDOT 31, o relógio projeta 35" in text
    assert "fez 2 fortes MAIS RÁPIDO que a faixa do plano" in text
    assert "50% do caminho até o relógio" in text


# --- no modelo de ritmos -------------------------------------------------------------------------


def _slow_history() -> TrainingHistory:
    """Quem só correu leve e submáximo: 10 km em 1:07 e rodagens a 6:50."""

    return TrainingHistory(activities=[_run(10, 6.7), _run(8, 6.85), _run(6, 6.9), _run(7, 6.9)])


def test_the_pace_model_follows_the_calibration_and_says_so():

    plain = PaceModelBuilder.build(_slow_history())

    calibration = Calibration(
        vdot=plain.vdot + 2.3, base_vdot=plain.vdot, garmin_vdot=plain.vdot + 4.5,
        weight=0.5, sessions=2,
    )

    with patch.object(pc, "for_runner", return_value=calibration):

        model = PaceModelBuilder.build(_slow_history(), SimpleNamespace(id="leonardo"))

    assert model.vdot == round(plain.vdot + 2.3, 1) or abs(model.vdot - (plain.vdot + 2.3)) < 0.1
    # limiar e VO2 ficam mais rápidos (pace menor); o aviso diz de onde vieram
    assert model.threshold < plain.threshold - 0.2 and model.interval < plain.interval - 0.2
    assert _pace_str(model.interval) != _pace_str(plain.interval)
    assert "Ritmos CALIBRADOS" in model.calibration_note
    assert plain.calibration_note is None


def test_without_calibration_the_model_is_exactly_what_it_was():

    with patch.object(pc, "for_runner", return_value=None):

        model = PaceModelBuilder.build(_slow_history(), SimpleNamespace(id="leonardo"))

    assert model.calibration_note is None
    assert model == PaceModelBuilder.build(_slow_history())


# --- a ligação com os dados ----------------------------------------------------------------------


def _wire(summary, prediction, race=False):

    return (
        patch("app.application.history.stimulus_delivery.for_profile", return_value=summary),
        patch(
            "app.infrastructure.persistence.race_prediction_repository.RacePredictionRepository.load",
            return_value=prediction,
        ),
        patch.object(pc, "recent_race", return_value=race),
    )


def test_the_runner_calibration_reads_the_stored_watch_the_sessions_and_the_races():

    pc._CACHE.clear()

    summary = SimpleNamespace(items=_two())

    patches = _wire(summary, GARMIN)

    for p in patches:

        p.start()

    try:

        runner = SimpleNamespace(id="leonardo")

        result = pc.for_runner(BASE_VDOT, runner, TODAY)

        assert result is not None and result.weight == 0.5

        # o segundo pedido (cache curto) não relê o storage
        with patch("app.application.history.stimulus_delivery.for_profile") as again:

            assert pc.for_runner(BASE_VDOT, runner, TODAY) is result
            again.assert_not_called()

    finally:

        for p in patches:

            p.stop()

        pc._CACHE.clear()


def test_the_runner_calibration_is_skipped_after_a_race_and_never_breaks_the_plan():

    pc._CACHE.clear()

    patches = _wire(SimpleNamespace(items=_two()), GARMIN, race=True)

    for p in patches:

        p.start()

    try:

        assert pc.for_runner(BASE_VDOT, SimpleNamespace(id="mauricio"), TODAY) is None

    finally:

        for p in patches:

            p.stop()

        pc._CACHE.clear()

    assert pc.for_runner(BASE_VDOT, None, TODAY) is None
    assert pc.for_runner(None, SimpleNamespace(id="x"), TODAY) is None

    with patch(
        "app.application.history.stimulus_delivery.for_profile", side_effect=RuntimeError("disco"),
    ):

        assert pc.for_runner(BASE_VDOT + 0.01, SimpleNamespace(id="x"), TODAY) is None

    pc._CACHE.clear()
