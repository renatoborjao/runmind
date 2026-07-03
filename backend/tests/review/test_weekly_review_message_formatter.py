from app.application.review.weekly_review_message_formatter import (
    WeeklyReviewMessageFormatter,
)


def _week(runs=1, distance_km=7.2, pace=5.99, hr=161.5,
          week_start="2026-06-29"):

    return {
        "week_start": week_start,
        "runs": runs,
        "distance_km": distance_km,
        "avg_pace_min_km": pace,
        "avg_hr": hr,
        "elevation_gain": 0,
    }


def _review(**overrides):

    defaults = dict(
        week_start="2026-06-29",
        comparison={
            "current_week": _week(),
            "previous_week": _week(
                runs=2,
                distance_km=14.1,
                pace=5.5,
                week_start="2026-06-22",
            ),
            "delta": {
                "distance_km": -6.9,
                "runs": -1,
                "avg_pace_min_km": 0.49,
                "avg_hr": 0,
                "volume_delta_percent": -48.9,
            },
        },
        trends={
            "volume": {"delta_percent": -11.7, "direction": "down"},
            "pace": {"delta_percent": -7.2, "direction": "down"},
        },
        consistency=66.7,
    )

    defaults.update(overrides)

    return defaults


def test_format_renders_full_message():

    message = WeeklyReviewMessageFormatter.format("Renato", _review())

    assert "Resumo da semana" in message
    assert "Fala, Renato! Fechando a semana de 29/06:" in message
    assert "• Volume: 7.2 km (14.1 km na anterior, -48.9%)" in message
    assert "• Treinos: 1 (2 na anterior)" in message
    assert "• Pace médio: 5:59 min/km (5:30 min/km na anterior)" in message
    assert "• Volume: caindo (-11.7%)" in message
    assert "• Pace: mais rápido (-7.2%)" in message
    assert "Consistência nas últimas semanas: 66.7%" in message


def test_format_returns_none_when_both_weeks_empty():

    review = _review(
        comparison={
            "current_week": _week(runs=0, distance_km=0, pace=None, hr=None),
            "previous_week": _week(runs=0, distance_km=0, pace=None, hr=None),
            "delta": {
                "distance_km": 0,
                "runs": 0,
                "avg_pace_min_km": None,
                "avg_hr": None,
                "volume_delta_percent": None,
            },
        },
    )

    assert WeeklyReviewMessageFormatter.format("Renato", review) is None


def test_format_handles_empty_previous_week_and_missing_trends():

    review = _review(
        comparison={
            "current_week": _week(),
            "previous_week": _week(runs=0, distance_km=0, pace=None, hr=None),
            "delta": {
                "distance_km": 7.2,
                "runs": 1,
                "avg_pace_min_km": None,
                "avg_hr": None,
                "volume_delta_percent": None,
            },
        },
        trends={
            "volume": {"delta_percent": None, "direction": "stable"},
            "pace": {"delta_percent": None, "direction": "stable"},
        },
    )

    message = WeeklyReviewMessageFormatter.format("Renato", review)

    # sem percentual quando a semana anterior é zerada
    assert "• Volume: 7.2 km (0.0 km na anterior)" in message
    # pace ausente vira travessão
    assert "(— na anterior)" in message
    # bloco de tendência é omitido por completo
    assert "Tendência" not in message


def test_format_translates_upward_trends():

    review = _review(
        trends={
            "volume": {"delta_percent": 12.0, "direction": "up"},
            "pace": {"delta_percent": 6.1, "direction": "up"},
        },
    )

    message = WeeklyReviewMessageFormatter.format("Renato", review)

    assert "• Volume: subindo (+12.0%)" in message
    assert "• Pace: mais lento (+6.1%)" in message
