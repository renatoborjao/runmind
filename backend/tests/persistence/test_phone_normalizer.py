from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)


def test_strips_whatsapp_jid_suffix():

    assert (
        PhoneNormalizer.normalize("5511999999999@s.whatsapp.net")
        == "5511999999999"
    )


def test_strips_plus_sign_from_stored_phone():

    assert PhoneNormalizer.normalize("+5511975658679") == "5511975658679"


def test_already_normalized_phone_is_unchanged():

    assert PhoneNormalizer.normalize("5511999999999") == "5511999999999"


def test_strips_spaces_and_dashes():

    assert PhoneNormalizer.normalize("+55 11 97565-8679") == "5511975658679"
