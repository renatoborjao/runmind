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
            "name": "correr 21 km com saúde", "has_race": True,
            "race_label": "10 km", "weeks_to_race": 5, "target_time": "00:50:00",
        }),
    )

    # a PROVA (10k) leva a contagem; o objetivo de fundo (21km) vem à parte
    assert "🎯 Rumo à prova" in message
    assert "• 10 km — faltam 5 semanas, alvo 00:50:00" in message
    assert "• Objetivo de fundo: correr 21 km com saúde" in message
    # a contagem NÃO cola no objetivo de fundo (o bug do Renato)
    assert "correr 21 km com saúde — faltam" not in message


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


def test_format_highlights_race_of_the_week_and_marks_pace():
    """Semana da prova: o resumo ABRE reconhecendo a prova (destaque) e marca
    o pace médio como puxado por ela. Era a queixa do Renato (resumo da semana
    da prova sem citar a prova)."""

    race = {
        "race_label": "10 km", "time": "54:18",
        "target_time": "00:55:00", "beat": True,
    }

    message = WeeklyReviewMessageFormatter.format(
        "Renato", _review(race=race),
    )

    assert "🏁 PROVA da semana: 10 km em 54:18 — você BATEU a meta de 00:55:00! 🏆" in message
    assert (
        "• Pace médio: 5:59 min/km (5:30 min/km na anterior) "
        "— inclui a prova (esforço máx)"
    ) in message


def test_format_race_highlight_missed_and_no_target():

    missed = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(race={"race_label": "10 km", "time": "56:00",
                      "target_time": "00:55:00", "beat": False}),
    )
    assert "🏁 PROVA da semana: 10 km em 56:00 (meta era 00:55:00)." in missed

    no_target = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(race={"race_label": "21 km", "time": "1:58:00",
                      "target_time": None, "beat": None}),
    )
    assert "🏁 PROVA da semana: 21 km em 1:58:00 — concluída! 🎉" in no_target


def test_format_plan_line_incoming_vs_external():

    ours = WeeklyReviewMessageFormatter.format(
        "Renato", _review(plan_incoming=True),
    )
    assert "Teu plano da próxima semana chega já já. Bora! 💪" in ours
    # não diz mais "semana que vem" (o plano chega no MESMO dia)
    assert "Semana que vem tem plano novo" not in ours

    external = WeeklyReviewMessageFormatter.format(
        "Renato", _review(plan_incoming=False),
    )
    assert "Teu plano da próxima semana chega já já" not in external


def _adherence_report(weeks_data, **overrides):
    """Report com uma tupla (done, planned) por semana, antiga -> recente."""

    from datetime import date, timedelta

    from app.domain.entities.adherence_report import (
        ADHERENCE_STABLE,
        AdherenceReport,
        WeekAdherence,
    )

    first = date(2026, 6, 1)

    weeks = [
        WeekAdherence(
            week_start=first + timedelta(days=7 * i),
            planned=planned,
            done=done,
        )
        for i, (done, planned) in enumerate(weeks_data)
    ]

    defaults = dict(weeks=weeks, rate=0.75, trend=ADHERENCE_STABLE)

    defaults.update(overrides)

    return AdherenceReport(**defaults)


def test_adherence_section_shows_series_and_pattern():

    from app.domain.entities.adherence_report import MissedPattern

    report = _adherence_report(
        [(3, 3), (2, 3), (3, 3), (1, 3)],
        missed_day=MissedPattern("Thursday", 3, 4),
        missed_type=MissedPattern("Intervalado", 3, 4),
    )

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence_history=report),
    )

    assert "🧭 Aderência ao plano" in message
    assert "• Últimas 4 semanas: 3/3 · 2/3 · 3/3 · 1/3 (75%)" in message
    assert "• Quinta-feira é o dia que mais escapa (3 de 4)" in message
    assert "• Treino que mais fica pra trás: Intervalado (3 de 4)" in message


def test_adherence_section_shows_only_last_four_weeks():

    report = _adherence_report([(3, 3)] * 6)

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence_history=report),
    )

    assert "• Últimas 4 semanas: 3/3 · 3/3 · 3/3 · 3/3 (100%)" in message


def test_adherence_rising_suppressed_when_series_is_perfect():
    """Bug do Renato: série exibida toda 3/3 NÃO pode dizer 'cumprindo mais que
    antes' — contradiz o que ele vê (é teto/estável, não crescente). O streak
    acima já celebra; a linha vira redundante e sem nexo."""

    from app.domain.entities.adherence_report import ADHERENCE_RISING

    report = _adherence_report([(3, 3)] * 4, trend=ADHERENCE_RISING)

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence_history=report),
    )

    assert "cumprindo mais que nas semanas anteriores" not in message


def test_adherence_rising_shown_when_series_actually_climbs():
    """Quando a série EXIBIDA sobe de verdade (1/3 → 3/3), aí sim faz sentido
    dizer que vem cumprindo mais."""

    from app.domain.entities.adherence_report import ADHERENCE_RISING

    report = _adherence_report(
        [(1, 3), (2, 3), (2, 3), (3, 3)],
        trend=ADHERENCE_RISING,
    )

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence_history=report),
    )

    assert "cumprindo mais que nas semanas anteriores" in message


def test_adherence_section_comments_falling_trend():

    from app.domain.entities.adherence_report import ADHERENCE_FALLING

    report = _adherence_report(
        [(3, 3), (3, 3), (1, 3), (1, 3)],
        trend=ADHERENCE_FALLING,
    )

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence_history=report),
    )

    assert "O cumprimento vem caindo" in message


def test_adherence_section_absent_with_single_week_or_no_report():
    """Uma semana só é o que a linha 'Treinos do plano' já diz; e review
    antigo (sem a chave) não pode quebrar."""

    uma_semana = _adherence_report([(2, 3)])

    message = WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(adherence_history=uma_semana),
    )

    assert "Aderência ao plano" not in message

    assert "Aderência ao plano" not in WeeklyReviewMessageFormatter.format(
        "Renato",
        _review(),
    )
