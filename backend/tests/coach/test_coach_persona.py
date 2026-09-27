from app.application.coach.writer.coach_persona import (
    COACH_VOICE,
    address_by_first_name,
    first_name,
)


def test_first_name():

    assert first_name("Renato Borges") == "Renato"
    assert first_name("Fernanda") == "Fernanda"
    assert first_name(None) == ""


def test_messages_address_athlete_by_first_name():
    """'Bom dia, Renato Borges!' soava robô — toda saída usa o primeiro nome."""

    assert address_by_first_name(
        "Renato Borges", "🏃 Bom dia, Renato Borges! Hoje é dia de treino"
    ) == "🏃 Bom dia, Renato! Hoje é dia de treino"

    # nome de uma palavra só / texto sem o nome: nada muda
    assert address_by_first_name("Fernanda", "Oi, Fernanda!") == "Oi, Fernanda!"
    assert address_by_first_name("Renato Borges", "Sem nome aqui") == "Sem nome aqui"


def test_voice_has_the_honesty_rules():

    for rule in ("PUXAR A ORELHA", "HONESTIDADE CALIBRADA", "PRECISÃO NA COBRANÇA"):

        assert rule in COACH_VOICE
