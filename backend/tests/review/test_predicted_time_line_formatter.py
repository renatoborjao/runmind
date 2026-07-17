from app.application.review.predicted_time_line_formatter import (
    PredictedTimeLineFormatter,
)


def test_none_when_no_prediction():

    assert PredictedTimeLineFormatter.line(None, "00:50:00") is None


def test_line_without_target_time_just_shows_the_prediction():

    line = PredictedTimeLineFormatter.line(
        {"formatted": "48:30", "delta_seconds": None, "delta_formatted": None},
        target_time=None,
    )

    assert line == "🔮 Se a prova fosse hoje: ~48:30"


def test_line_faster_than_target():

    line = PredictedTimeLineFormatter.line(
        {"formatted": "48:30", "delta_seconds": -90, "delta_formatted": "1:30"},
        target_time="00:50:00",
    )

    assert "já bateria a meta de 00:50:00 com ~1:30 de sobra" in line


def test_line_slower_than_target():

    line = PredictedTimeLineFormatter.line(
        {"formatted": "52:00", "delta_seconds": 120, "delta_formatted": "2:00"},
        target_time="00:50:00",
    )

    assert "faltam ~2:00 pra bater a meta de 00:50:00" in line
