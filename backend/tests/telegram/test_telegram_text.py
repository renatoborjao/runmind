from app.infrastructure.integrations.telegram.telegram_text import (
    to_plain_text,
)


def test_double_asterisk_bold_is_stripped():

    assert to_plain_text("**Terça-feira (30/06):**") == "Terça-feira (30/06):"


def test_bullets_become_dots():

    text = "* Rodagem leve\n* 3.5 km"

    assert to_plain_text(text) == "• Rodagem leve\n• 3.5 km"


def test_dash_and_plus_bullets_become_dots():

    assert to_plain_text("- item\n+ outro") == "• item\n• outro"


def test_single_asterisk_emphasis_is_stripped():

    assert to_plain_text("ritmo *confortável* hoje") == "ritmo confortável hoje"


def test_headers_are_flattened():

    assert to_plain_text("### Plano da semana") == "Plano da semana"


def test_bullet_with_inline_bold_is_clean():

    assert to_plain_text("* **Sábado:** longão") == "• Sábado: longão"


def test_plain_text_is_untouched():

    text = "Seu plano da semana, Renato, é o seguinte:"

    assert to_plain_text(text) == text


def test_arithmetic_asterisk_is_not_treated_as_emphasis():

    assert to_plain_text("faça 3 * 4 repetições") == "faça 3 * 4 repetições"
