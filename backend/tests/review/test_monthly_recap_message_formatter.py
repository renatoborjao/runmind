from app.application.review.monthly_recap_message_formatter import (
    MonthlyRecapMessageFormatter,
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


def test_message_carries_the_numbers_and_signature():

    message = MonthlyRecapMessageFormatter.format(
        "Renato", _recap(), narrative=["Mês forte, parabéns!"],
    )

    assert "Recap de Julho/2026" in message
    assert "Renato fechou Julho/2026 com:" in message
    assert "85.0 km em 12 treino(s)" in message
    assert "Maior treino do mês: 15.0 km" in message
    assert "Consistência: 78%" in message
    assert "Mês forte, parabéns!" in message
    assert "Feito com 🏃 RunMind" in message

    # nudge de indicação (crescimento orgânico) — sem link/contato fixo,
    # o próprio texto sendo encaminhado já é o mecanismo
    assert "Passa esse recap" in message


def test_message_includes_records_section_when_present():

    message = MonthlyRecapMessageFormatter.format(
        "Renato",
        _recap(records=["🏆 Corrida mais longa: 15.0 km"]),
        narrative=["Boa!"],
    )

    assert "Recordes batidos neste mês:" in message
    assert "🏆 Corrida mais longa: 15.0 km" in message


def test_message_includes_predicted_time_line_when_present():

    message = MonthlyRecapMessageFormatter.format(
        "Renato",
        {
            **_recap(),
            "target_time": "00:50:00",
            "predicted_time": {
                "formatted": "48:30",
                "delta_seconds": -90,
                "delta_formatted": "1:30",
            },
        },
        narrative=["Boa!"],
    )

    assert "🔮 Se a prova fosse hoje: ~48:30" in message
    assert "já bateria a meta de 00:50:00 com ~1:30 de sobra" in message


def test_message_omits_predicted_time_line_when_absent():

    message = MonthlyRecapMessageFormatter.format(
        "Renato",
        {**_recap(), "predicted_time": None},
        narrative=["Boa!"],
    )

    assert "🔮" not in message


def test_message_omits_records_section_when_empty():

    message = MonthlyRecapMessageFormatter.format(
        "Renato", _recap(records=[]), narrative=["Boa!"],
    )

    assert "Recordes batidos neste mês:" not in message


def test_falls_back_to_deterministic_narrative_when_ai_is_none():

    message = MonthlyRecapMessageFormatter.format(
        "Renato", _recap(), narrative=None,
    )

    assert "Mais um mês de treino na conta" in message
    assert "12 treino(s)" in message
