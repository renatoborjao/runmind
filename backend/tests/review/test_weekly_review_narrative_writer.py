from unittest.mock import patch

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


def test_facts_include_long_term_brief_when_profile_given():
    """A leitura da semana fala com quem o atleta é: quando há profile, injeta o
    brief de longo prazo (memória/aprendizados/evolução). LEI base-histórico."""

    with patch(
        "app.application.coach.context.athlete_brief."
        "AthleteLongTermBrief.render",
        return_value="QUEM É O ATLETA NO LONGO PRAZO:\nMemória: prefere rua",
    ):

        facts = WeeklyReviewNarrativeWriter._facts(
            "Renato", _review({"name": "saúde"}), profile="renato",
        )

    assert "QUEM É O ATLETA NO LONGO PRAZO" in facts
    assert "prefere rua" in facts


def test_facts_omit_brief_without_profile():
    """Sem profile (compatibilidade), nenhum brief é puxado — comportamento
    de antes."""

    facts = WeeklyReviewNarrativeWriter._facts("Renato", _review({"name": "saúde"}))

    assert "QUEM É O ATLETA NO LONGO PRAZO" not in facts


def test_facts_frame_a_race_goal():
    """Objetivo com prova: os fatos enquadram como marca + contagem regressiva
    (a IA deve falar de progresso rumo à prova)."""

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato",
        _review({
            "name": "correr 21 km com saúde", "has_race": True,
            "race_label": "10 km", "weeks_to_race": 5, "target_time": "00:50:00",
        }),
    )

    # a PROVA (10k) é distinta do OBJETIVO de fundo (21km) — não conflar
    assert "Próxima prova: 10 km" in facts
    assert "faltam 5 semanas" in facts
    assert "alvo 00:50:00" in facts
    assert "Objetivo de fundo: correr 21 km com saúde" in facts


def test_facts_include_predicted_time_when_present():

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato",
        _review({
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
            "predicted_time": {"formatted": "52:00"},
        }),
    )

    assert "Previsão no ritmo atual: 52:00." in facts


def test_facts_omit_predicted_time_when_absent():

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato",
        _review({
            "name": "10 km sub-50", "has_race": True,
            "weeks_to_race": 5, "target_time": "00:50:00",
        }),
    )

    assert "Previsão no ritmo atual" not in facts


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


def test_facts_highlight_race_of_the_week():
    """Semana com prova: os fatos trazem a prova como DESTAQUE e avisam que o
    pace médio está puxado por ela (pra a IA não ler como evolução de treino).
    Era a queixa do Renato."""

    review = _review({"name": "saúde", "has_race": False})
    review["race"] = {
        "race_label": "10 km", "time": "54:18",
        "target_time": "00:55:00", "beat": True,
    }

    facts = WeeklyReviewNarrativeWriter._facts("Renato", review)

    assert "DESTAQUE DA SEMANA — PROVA: 10 km em 54:18 (BATEU a meta de 00:55:00)" in facts
    assert "CELEBRE" in facts
    assert "pace médio da semana está PUXADO" in facts


def test_facts_without_race_have_no_highlight():

    facts = WeeklyReviewNarrativeWriter._facts(
        "Renato", _review({"name": "saúde", "has_race": False}),
    )

    assert "DESTAQUE DA SEMANA" not in facts


def test_parse_valid_and_invalid():

    assert WeeklyReviewNarrativeWriter._parse(
        '{"reading": ["Semana firme.", "Segue assim!"]}'
    ) == ["Semana firme.", "Segue assim!"]

    assert WeeklyReviewNarrativeWriter._parse("lixo") is None
    assert WeeklyReviewNarrativeWriter._parse('{"reading": []}') is None
