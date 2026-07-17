from app.application.review.monthly_recap_narrative_writer import (
    MonthlyRecapNarrativeWriter,
)


def _recap(records=None):

    return {
        "month_label": "Julho/2026",
        "total_km": 85.0,
        "total_runs": 12,
        "longest_km": 15.0,
        "consistency": 78.0,
        "records": records or [],
    }


def test_facts_carry_the_numbers():

    facts = MonthlyRecapNarrativeWriter._facts("Renato", _recap())

    assert "Mês: Julho/2026" in facts
    assert "Total: 85.0 km em 12 treino(s)" in facts
    assert "Maior treino do mês: 15.0 km" in facts
    assert "Consistência do mês: 78%" in facts
    assert "Nenhum recorde novo neste mês." in facts


def test_facts_list_records_when_present():

    facts = MonthlyRecapNarrativeWriter._facts(
        "Renato",
        _recap(records=["🏆 Corrida mais longa: 15.0 km"]),
    )

    assert "Recordes batidos neste mês: 🏆 Corrida mais longa: 15.0 km" in facts


def test_facts_include_predicted_time_when_present():

    facts = MonthlyRecapNarrativeWriter._facts(
        "Renato",
        {**_recap(), "predicted_time": {"formatted": "48:30"}},
    )

    assert "Previsão de prova no ritmo atual: 48:30." in facts


def test_facts_omit_predicted_time_when_absent():

    facts = MonthlyRecapNarrativeWriter._facts(
        "Renato",
        {**_recap(), "predicted_time": None},
    )

    assert "Previsão de prova" not in facts


def test_parse_valid_and_invalid():

    assert MonthlyRecapNarrativeWriter._parse(
        '{"reading": ["Mês forte!", "Parabéns."]}'
    ) == ["Mês forte!", "Parabéns."]

    assert MonthlyRecapNarrativeWriter._parse("lixo") is None
    assert MonthlyRecapNarrativeWriter._parse('{"reading": []}') is None
