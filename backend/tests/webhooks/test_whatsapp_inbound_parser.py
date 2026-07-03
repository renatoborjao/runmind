from app.infrastructure.integrations.evolution.inbound_parser import (
    WhatsAppInboundParser,
)


def test_extracts_text_from_conversation_field():

    data = {
        "message": {
            "conversation": "Bom dia coach",
        },
    }

    assert WhatsAppInboundParser.extract_text(data) == "Bom dia coach"


def test_extracts_text_from_extended_text_message():

    data = {
        "message": {
            "extendedTextMessage": {
                "text": "Respondendo uma mensagem anterior",
            },
        },
    }

    assert (
        WhatsAppInboundParser.extract_text(data)
        == "Respondendo uma mensagem anterior"
    )


def test_returns_none_when_no_recognized_text_field():

    data = {
        "message": {
            "imageMessage": {
                "caption": "legenda",
            },
        },
    }

    assert WhatsAppInboundParser.extract_text(data) is None


def test_returns_none_when_message_missing():

    assert WhatsAppInboundParser.extract_text({}) is None


def test_identifies_group_jid_as_group_message():

    assert WhatsAppInboundParser.is_group_message(
        "120363424166337657@g.us",
    ) is True


def test_identifies_broadcast_jid_as_group_message():

    assert WhatsAppInboundParser.is_group_message(
        "status@broadcast",
    ) is True


def test_direct_chat_jid_is_not_a_group_message():

    assert WhatsAppInboundParser.is_group_message(
        "5511975658679@s.whatsapp.net",
    ) is False
