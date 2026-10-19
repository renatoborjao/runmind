"""A previsão de prova em FAIXA (histórico × Garmin). Caso real — Leonardo, 18/10,
primeira prova (10 km, meta 1:00:00): no chat o coach disse "base pronta pra 1h com
segurança" (Garmin: 56:33) e, no resumo das 19h, "se a prova fosse hoje ~1:05:32"
(o melhor esforço real). Duas respostas do mesmo coach no mesmo dia. Agora, quando as
duas fontes discordam, o coach fala de um intervalo rotulado e a meta se posiciona
dentro dele."""

from datetime import date
from unittest.mock import patch

from app.application.coach.planning.race_projection_directive import (
    race_projection_directive,
)
from app.application.history.race_forecast import (
    build_range,
    garmin_seconds_for,
    range_sentence,
)
from app.application.history.race_time_predictor import RaceTimePredictor
from app.application.review.goal_projection_writer import GoalProjectionWriter
from app.application.review.predicted_time_line_formatter import (
    PredictedTimeLineFormatter,
)
from app.domain.entities.race_prediction import RacePrediction
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory

# Leonardo em 19/10 (projeção do Garmin) e o que o histórico dele diz pra 10 km
LEONARDO_GARMIN = RacePrediction(
    time_5k_sec=1570, time_10k_sec=3393, time_half_sec=7792, time_marathon_sec=17601,
)

HISTORY_10K = 3932.0  # 1:05:32

PRED = "app.application.history.race_time_predictor.RaceTimePredictor.predict"
REPO = "app.infrastructure.persistence.race_prediction_repository.RacePredictionRepository.load"


def _goal(target="01:00:00", distance=10.0, race_date=date(2026, 12, 20)):

    return TrainingGoal(
        name="10 km", distance_km=distance, target_time=target,
        race_date=race_date, priority="A",
    )


def _predict(garmin=LEONARDO_GARMIN, history=HISTORY_10K, target="01:00:00",
             distance=10.0, profile="leonardo"):

    with (
        patch(PRED, return_value={"predicted_seconds": history,
                                  "anchor_distance_km": 5.0, "anchor_date": "2026-10-10"}),
        patch(REPO, return_value=garmin),
    ):

        return RaceTimePredictor.predict_formatted(
            TrainingHistory(activities=[]), distance, target, profile=profile,
        )


# ---- o tempo do Garmin pra QUALQUER distância ------------------------------------


def test_garmin_exact_for_the_four_standard_distances():

    assert garmin_seconds_for(LEONARDO_GARMIN, 10.0) == 3393
    assert garmin_seconds_for(LEONARDO_GARMIN, 5.0) == 1570
    assert garmin_seconds_for(LEONARDO_GARMIN, 21.0975) == 7792
    assert garmin_seconds_for(LEONARDO_GARMIN, 42.195) == 17601


def test_garmin_for_a_15k_is_riegel_from_the_closest_distance():

    fifteen = garmin_seconds_for(LEONARDO_GARMIN, 15.0)

    # 15 km está mais perto (em razão) da meia (1.41) que dos 10K (1.5): vem da meia
    expected = 7792 * (15.0 / 21.0975) ** 1.06

    assert abs(fifteen - expected) < 1
    assert 3393 < fifteen < 7792


def test_garmin_beyond_reach_or_without_data_is_none():

    assert garmin_seconds_for(LEONARDO_GARMIN, 150.0) is None
    assert garmin_seconds_for(None, 10.0) is None
    assert garmin_seconds_for(RacePrediction(), 10.0) is None
    assert garmin_seconds_for(LEONARDO_GARMIN, None) is None


# ---- quando vira faixa -----------------------------------------------------------


def test_sources_that_disagree_become_a_range_with_labels():

    forecast = build_range(HISTORY_10K, 3393)

    assert forecast.is_range
    assert forecast.low_label == "Garmin"
    assert forecast.high_label == "seus treinos"

    assert range_sentence(forecast.to_dict()) == (
        "entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)"
    )


def test_labels_follow_the_values_when_garmin_is_the_slow_one():

    forecast = build_range(3300, 3900)

    assert forecast.low_label == "seus treinos"
    assert forecast.high_label == "Garmin"


def test_sources_within_four_percent_are_one_number():
    """Ruído não é discordância: nada de faixa pra 50:00 × 51:00."""

    assert not build_range(3000, 3060).is_range
    assert build_range(3000, 3200).is_range


def test_range_needs_both_sources():

    assert build_range(None, 3393) is None
    assert build_range(HISTORY_10K, None) is None


def test_where_the_target_falls_in_the_range():

    forecast = build_range(HISTORY_10K, 3393)

    assert forecast.position_of(3600) == "inside"   # 1:00:00 — o caso do Leonardo
    assert forecast.position_of(4200) == "beaten"   # 1:10:00 — já bate no cenário lento
    assert forecast.position_of(3000) == "beyond"   # 50:00 — mais rápida que tudo
    # a poucos segundos da ponta rápida é empate técnico, não "falta" (João: 23:03 × 23:00)
    assert forecast.position_of(3393 - 15) == "inside"
    assert forecast.position_of(3393 - 25) == "beyond"


# ---- predict_formatted -----------------------------------------------------------


def test_predict_formatted_carries_the_range_for_leonardo():

    out = _predict()

    assert out["formatted"] == "1:05:32"   # o número do histórico segue o de sempre
    assert out["seconds"] == HISTORY_10K
    assert out["range"]["low_formatted"] == "56:33"
    assert out["range"]["high_formatted"] == "1:05:32"
    assert out["range"]["position"] == "inside"


def test_without_profile_or_garmin_it_is_the_old_single_number():

    assert "range" not in _predict(profile=None)
    assert "range" not in _predict(garmin=None)
    assert "range" not in _predict(garmin=RacePrediction(time_10k_sec=3900))


def test_a_failure_loading_the_garmin_never_breaks_the_forecast():

    with (
        patch(PRED, return_value={"predicted_seconds": HISTORY_10K}),
        patch(REPO, side_effect=OSError("disco")),
    ):

        out = RaceTimePredictor.predict_formatted(
            TrainingHistory(activities=[]), 10.0, "01:00:00", profile="leonardo",
        )

    assert out["formatted"] == "1:05:32"
    assert "range" not in out


# ---- a linha do resumo de domingo ---------------------------------------------------


def test_summary_line_for_leonardo_shows_the_range_and_where_the_goal_sits():

    line = PredictedTimeLineFormatter.line(_predict(), "01:00:00")

    assert line.startswith(
        "🔮 Se a prova fosse hoje: entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)"
    )
    assert "a meta de 01:00:00 cabe nessa faixa" in line
    assert "consistência nos treinos" in line


def test_summary_line_when_the_goal_is_slower_than_the_whole_range():

    line = PredictedTimeLineFormatter.line(_predict(target="01:10:00"), "01:10:00")

    assert "já bateria a meta de 01:10:00, mesmo no cenário mais lento" in line


def test_summary_line_when_the_goal_is_faster_than_the_whole_range():

    line = PredictedTimeLineFormatter.line(_predict(target="00:50:00"), "00:50:00")

    assert "faltam ~6:33 pra bater a meta de 00:50:00 mesmo no cenário mais rápido" in line


def test_summary_line_without_range_is_unchanged():

    out = _predict(profile=None)

    assert PredictedTimeLineFormatter.line(out, "01:00:00") == (
        "🔮 Se a prova fosse hoje: ~1:05:32 — faltam ~5:32 pra bater a meta de 01:00:00"
    )


# ---- "rumo à meta" -----------------------------------------------------------------


def _writer(target, **kw):

    with (
        patch(PRED, return_value={"predicted_seconds": HISTORY_10K}),
        patch(REPO, return_value=LEONARDO_GARMIN),
    ):

        return GoalProjectionWriter.write(
            "Leonardo", _goal(target), TrainingHistory(activities=[]),
            weeks_to_race=9, profile="leonardo", **kw,
        )


def test_goal_block_for_leonardo_speaks_the_range_not_one_number():

    text = _writer("01:00:00")

    assert "Hoje, teu tempo fica entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)" in text
    assert "o Garmin estima pelo teu VO₂máx" in text
    assert "Tua meta de 01:00:00 cabe na faixa" in text
    # a franqueza velha ("bem acima do que se ganha num ciclo") contradiria a faixa
    assert "Sendo franco" not in text
    assert "~*1:05:32*" not in text


def test_goal_block_when_the_goal_is_beyond_the_range_measures_from_the_fast_end():

    text = _writer("00:50:00")

    assert "entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)" in text
    # 6:33 a recuperar (do cenário mais rápido), não 15:32 (do lento)
    assert "faltam ~*6:33*" in text


def test_goal_block_when_both_measures_beat_the_goal():

    text = _writer("01:10:00")

    assert "pelas duas medidas você JÁ está no ritmo da tua meta de 01:10:00" in text


def test_goal_block_without_garmin_is_the_old_text():

    with (
        patch(PRED, return_value={"predicted_seconds": HISTORY_10K}),
        patch(REPO, return_value=None),
    ):

        text = GoalProjectionWriter.write(
            "Leonardo", _goal("01:00:00"), TrainingHistory(activities=[]),
            weeks_to_race=9, profile="leonardo",
        )

    assert "No teu nível atual, teu tempo seria ~*1:05:32*." in text
    assert "faixa" not in text.split("Sendo franco")[0]


def test_the_news_snapshot_keeps_the_history_number():
    """O "rumo à meta" só reaparece quando a projeção ANDA — a conta do histórico,
    não a faixa, é o que ele compara semana a semana."""

    with (
        patch(PRED, return_value={"predicted_seconds": HISTORY_10K}),
        patch(REPO, return_value=LEONARDO_GARMIN),
    ):

        built = GoalProjectionWriter.section(
            "Leonardo", _goal("01:00:00"), TrainingHistory(activities=[]),
            weeks_to_race=9, profile="leonardo",
        )

    assert built is not None

    text, snapshot = built

    assert snapshot["seconds"] == HISTORY_10K
    assert "entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)" in text


# ---- o chat: a diretriz ensina a falar em faixa ------------------------------------


def test_directive_teaches_the_coach_to_speak_the_range():

    out = race_projection_directive(
        LEONARDO_GARMIN, _goal("01:00:00"), history_seconds=HISTORY_10K,
    )

    assert "AO FALAR COM O ATLETA" in out
    assert "use a FAIXA" in out
    assert "entre ~56:33 (Garmin) e ~1:05:32 (seus treinos)" in out
    assert "com segurança" in out   # a proibição de prometer a marca
    # o que já existia segue
    assert "ESTIMATIVA" in out and "não decreto" in out


def test_directive_without_the_history_never_lets_garmin_stand_alone_as_certain():

    out = race_projection_directive(LEONARDO_GARMIN, _goal("01:00:00"))

    assert "AO FALAR COM O ATLETA" in out
    assert "não cite só o número do Garmin como certo" in out
    assert "use a FAIXA" not in out


def test_directive_with_agreeing_sources_does_not_invent_a_range():

    out = race_projection_directive(LEONARDO_GARMIN, _goal("01:00:00"), history_seconds=3450)

    assert "use a FAIXA" not in out
    assert "não cite só o número do Garmin como certo" in out


def test_directive_for_a_15k_uses_the_estimated_garmin_time():

    # Garmin pra 15 km (Riegel a partir da meia) ≈ 1:30:28; o histórico diz 1:40:00
    out = race_projection_directive(
        LEONARDO_GARMIN, _goal("01:22:30", distance=15.0), history_seconds=6000,
    )

    assert "use a FAIXA" in out
    assert "entre ~1:30:28 (Garmin) e ~1:40:00 (seus treinos)" in out

    # histórico perto do estimado do Garmin: sem faixa
    near = race_projection_directive(
        LEONARDO_GARMIN, _goal("01:22:30", distance=15.0), history_seconds=5400,
    )

    assert "use a FAIXA" not in near


def test_joao_goal_a_few_seconds_from_the_garmin_end_is_inside_not_already_there():
    """Real: Garmin 23:03 × treinos 25:23, meta 23:00. A ponta rápida não pode
    virar "você JÁ está no ritmo" (os treinos dizem 2:23 de distância)."""

    garmin = RacePrediction(time_5k_sec=1383, time_10k_sec=3035)

    with (
        patch(PRED, return_value={"predicted_seconds": 1523.0}),
        patch(REPO, return_value=garmin),
    ):

        out = RaceTimePredictor.predict_formatted(
            TrainingHistory(activities=[]), 5.0, "00:23:00", profile="joaosoares",
        )

        text = GoalProjectionWriter.write(
            "João", _goal("00:23:00", distance=5.0), TrainingHistory(activities=[]),
            profile="joaosoares",
        )

    assert out["range"]["position"] == "inside"
    assert "entre ~23:03 (Garmin) e ~25:23 (seus treinos)" in text
    assert "cabe na faixa" in text
    assert "JÁ está no ritmo" not in text
    assert "a prova que a prova diz" not in text
