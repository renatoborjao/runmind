from app.application.coach.writer.help_menu import HelpMenu


def test_card_lists_the_main_questions():
    """O cardápio cobre os pedidos principais, com o nome do atleta."""

    card = HelpMenu.card("Renato")

    assert "Renato" in card
    assert "próximo treino" in card
    assert "plano da semana" in card
    assert "Como está meu corpo" in card
    assert "Estou evoluindo" in card
    assert "Como estou" in card          # o retrato


def test_weekly_tip_rotates_and_wraps():
    """Cada semana traz uma dica diferente; o ciclo dá a volta sem estourar."""

    n = len(HelpMenu._TIPS)

    tips = [HelpMenu.weekly_tip(i) for i in range(n)]

    # todas distintas dentro de um ciclo
    assert len(set(tips)) == n

    # dá a volta: semana n cai na mesma dica da semana 0
    assert HelpMenu.weekly_tip(n) == HelpMenu.weekly_tip(0)


def test_weekly_tip_always_flags_you_can_ask():
    """Toda dica é uma pista de descoberta (começa com o selo 💡)."""

    for i in range(len(HelpMenu._TIPS)):

        assert HelpMenu.weekly_tip(i).startswith("💡")
