from app.infrastructure.integrations.whatsapp_cloud.whatsapp_cloud_inbound_parser import (
    WhatsAppCloudInboundParser as Parser,
)


def _payload(message: dict, contact_name: str = "Renato") -> dict:

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1760347958479071",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [
                                {
                                    "profile": {"name": contact_name},
                                    "wa_id": "5511976483800",
                                }
                            ],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def _text_message(body: str) -> dict:

    return {
        "from": "5511976483800",
        "id": "wamid.ABC",
        "timestamp": "1783625000",
        "type": "text",
        "text": {"body": body},
    }


def test_extracts_text_and_sender():

    payload = _payload(_text_message("Bom dia coach"))

    parsed = Parser.first_message(payload)

    assert parsed is not None
    assert Parser.sender_phone(parsed["message"]) == "5511976483800"
    assert Parser.sender_name(parsed["value"]) == "Renato"
    assert Parser.extract_text(parsed["message"]) == "Bom dia coach"
    assert Parser.extract_media(parsed["message"]) is None


def test_status_only_payload_has_no_message():

    # Meta manda "entregue/lido" sem messages[] — não é conversa
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [{"status": "delivered"}],
                        }
                    }
                ]
            }
        ]
    }

    assert Parser.first_message(payload) is None


def test_extracts_image_media():

    image_msg = {
        "from": "5511976483800",
        "id": "wamid.IMG",
        "type": "image",
        "image": {
            "id": "MEDIA123",
            "mime_type": "image/jpeg",
            "caption": "meu plano da semana",
        },
    }

    parsed = Parser.first_message(_payload(image_msg))

    media = Parser.extract_media(parsed["message"])

    assert media == {
        "media_id": "MEDIA123",
        "mimetype": "image/jpeg",
        "caption": "meu plano da semana",
    }

    # legenda da imagem vira o texto (intenção do atleta)
    assert Parser.extract_text(parsed["message"]) == "meu plano da semana"


def test_unsupported_media_is_ignored():

    audio_msg = {
        "from": "5511976483800",
        "type": "audio",
        "audio": {"id": "AUD1", "mime_type": "audio/ogg"},
    }

    parsed = Parser.first_message(_payload(audio_msg))

    assert Parser.extract_media(parsed["message"]) is None
    assert Parser.extract_text(parsed["message"]) is None
