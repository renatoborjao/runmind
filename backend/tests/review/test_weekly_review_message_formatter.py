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
    assert "Fala, Renato! Fechando a semana de 29/06." in message
    assert "📝 Como foi sua semana" in message
    assert "• Volume: 7.2 km (14.1 km na anterior, -48.9%)" in message
    assert "• Treinos: 1 (2 na anterior)" in message
    assert "• Pace médio: 5:59 min/km (5:30 min/km na anterior)" in message
    assert "• Volume: caindo (-11.7%)" in message
    assert "• Pace: mais rápido (-7.2%)" in message
    assert "Consistência nas últimas semanas: 67%" in message


def test_format_uses_ai_narrative_when_given():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(),
        narrative=["Semana sólida rumo ao sub-50.", "Segue firme!"],
    )

    assert "Semana sólida rumo ao sub-50." in message
    assert "Você fechou a semana com" not in message  # não usa o fallback


def test_format_uses_fallback_narrative_when_none():

    message = WeeklyReviewMessageFormatter.format("Renato", _review())

    assert "Você fechou a semana com 1 treino(s) e 7.2 km" in message


def test_format_shows_adherence_and_longest():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence={"planned": 3, "done": 3}, longest_km=12.0),
    )

    assert "• Treinos do plano: 3 de 3 ✅" in message
    assert "• Longão da semana: 12.0 km" in message
    # com aderência, some a contagem simples de treinos
    assert "• Treinos: 1 (2 na anterior)" not in message


def test_format_shows_race_goal_countdown():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(goal={
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
        }),
    )

    assert "🎯 Rumo à meta" in message
    assert "• 10 km sub-50 — faltam 5 semanas, alvo 00:50:00" in message


def test_format_shows_predicted_race_time_faster_than_target():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(goal={
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
            "predicted_time": {
                "formatted": "48:30",
                "delta_seconds": -90,
                "delta_formatted": "1:30",
            },
        }),
    )

    assert "🔮 Se a prova fosse hoje: ~48:30" in message
    assert "já bateria a meta de 00:50:00 com ~1:30 de sobra" in message


def test_format_shows_predicted_race_time_slower_than_target():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(goal={
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
            "predicted_time": {
                "formatted": "52:00",
                "delta_seconds": 120,
                "delta_formatted": "2:00",
            },
        }),
    )

    assert "🔮 Se a prova fosse hoje: ~52:00" in message
    assert "faltam ~2:00 pra bater a meta de 00:50:00" in message


def test_format_omits_predicted_line_when_no_anchor():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(goal={
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
            "predicted_time": None,
        }),
    )

    assert "🔮" not in message


def test_format_shows_health_goal_without_countdown():

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(goal={"name": "saúde e emagrecer", "has_race": False}),
    )

    assert "🎯 Seu objetivo" in message
    assert "• saúde e emagrecer" in message
    assert "faltam" not in message  # sem cobrança de prazo/prova


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
