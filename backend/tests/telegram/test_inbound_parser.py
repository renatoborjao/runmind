from app.infrastructure.integrations.telegram.telegram_inbound_parser import (
    TelegramInboundParser,
)


def _update(message: dict) -> dict:

    return {"update_id": 1, "message": message}


def _base_message(**overrides) -> dict:

    msg = {
        "message_id": 10,
        "from": {"id": 42, "is_bot": False, "first_name": "Renato"},
        "chat": {"id": 42, "type": "private"},
        "text": "oi coach",
    }

    msg.update(overrides)

    return msg


def test_extracts_chat_id_text_and_name():

    msg = _base_message()

    assert TelegramInboundParser.chat_id(msg) == "42"
    assert TelegramInboundParser.extract_text(msg) == "oi coach"
    assert TelegramInboundParser.sender_name(msg) == "Renato"
    assert TelegramInboundParser.is_from_bot(msg) is False


def test_bot_message_is_flagged():

    msg = _base_message(**{"from": {"id": 1, "is_bot": True}})

    assert TelegramInboundParser.is_from_bot(msg) is True


def test_photo_becomes_media_with_largest_resolution():

    msg = _base_message(
        text=None,
        caption="meu treino",
        photo=[
            {"file_id": "small", "width": 90},
            {"file_id": "big", "width": 1280},
        ],
    )

    media = TelegramInboundParser.extract_media(msg)

    assert media == {
        "file_id": "big",
        "mimetype": "image/jpeg",
        "caption": "meu treino",
    }

    # legenda também vale como texto
    assert TelegramInboundParser.extract_text(msg) == "meu treino"


def test_supported_document_becomes_media():

    msg = _base_message(
        text=None,
        document={
            "file_id": "doc1",
            "mime_type": "application/pdf",
            "file_name": "treino.pdf",
        },
    )

    media = TelegramInboundParser.extract_media(msg)

    assert media["file_id"] == "doc1"
    assert media["mimetype"] == "application/pdf"


def test_unsupported_document_is_ignored():

    msg = _base_message(
        text=None,
        document={"file_id": "x", "mime_type": "application/zip"},
    )

    assert TelegramInboundParser.extract_media(msg) is None


def test_plain_text_has_no_media():

    assert TelegramInboundParser.extract_media(_base_message()) is None


def test_non_message_update_returns_none():

    assert TelegramInboundParser.message({"edited_message": {}}) is None


def test_update_id_is_extracted_as_string():

    assert TelegramInboundParser.update_id({"update_id": 987}) == "987"
    assert TelegramInboundParser.update_id({}) is None
