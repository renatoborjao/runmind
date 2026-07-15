from app.application.review.weekly_review_narrative_writer import (
    WeeklyReviewNarrativeWriter,
)


def _review(goal: dict) -> dict:

    return {
        "comparison": {
            "current_week": {
                "runs": 3, "distance_km": 28.0, "avg_pace_min_km": 5.5,
            },
            "previous_week": {
                "runs": 3, "distance_km": 26.0, "avg_pace_min_km": 5.6,
            },
            "delta": {"volume_delta_percent": 7.7},
        },
        "trends": {
            "volume": {"delta_percent": 8.0, "direction": "up"},
            "pace": {"delta_percent": -3.0, "direction": "down"},
        },
        "consistency": 85.0,
        "goal": goal,
        "adherence": {"planned": 3, "done": 3},
        "longest_km": 12.0,
    }


def test_facts_frame_a_race_goal():
    """Objetivo com prova: os fatos enquadram como marca + contagem regressiva
    (a IA deve falar de progresso rumo à prova)."""

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato",
        _review({
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
        }),
    )

    assert "PROVA/MARCA" in facts
    assert "faltam 5 semanas" in facts
    assert "alvo 00:50:00" in facts


def test_facts_frame_a_health_goal():
    """Objetivo sem prova: os fatos mandam NÃO cobrar pace de prova."""

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato",
        _review({"name": "saúde e emagrecer", "has_race": False}),
    )

    assert "SEM prova" in facts
    assert "NÃO cobre pace" in facts


def test_facts_carry_the_numbers():

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato",
        _review({"name": "saúde", "has_race": False}),
    )

    assert "Volume: 28.0 km" in facts
    assert "Aderência ao plano: 3 de 3" in facts
    assert "Maior treino da semana: 12.0 km" in facts
    assert "Consistência recente: 85%" in facts


def test_parse_valid_and_invalid():

    assert WeeklyReviewNarrativeWriter._parse(
        '{"reading": ["Semana firme.", "Segue assim!"]}'
    ) == ["Semana firme.", "Segue assim!"]

    assert WeeklyReviewNarrativeWriter._parse("lixo") is None
    assert WeeklyReviewNarrativeWriter._parse('{"reading": []}') is None
