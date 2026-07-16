from app.infrastructure.integrations.evolution.inbound_parser import (
    SUPPORTED_MEDIA_MIMETYPES,
)

# extensão -> mimetype para fotos do Telegram (que não trazem mimetype)
PHOTO_MIMETYPE = "image/jpeg"


class TelegramInboundParser:
    """Extrai o essencial de um update do Telegram, no mesmo formato
    que o parser do WhatsApp entrega ao roteamento compartilhado."""

    @staticmethod
    def message(update: dict) -> dict | None:
        """Retorna a `message` do update (ignora edições, callbacks,
        canais). None quando não há mensagem tratável."""

        return update.get("message")

    @staticmethod
    def update_id(update: dict) -> str | None:
        """Id sequencial do update — chave de idempotência: o Telegram
        reentrega o MESMO update_id quando o ack demora, e sem dedup cada
        reentrega vira um "me embananei" novo pro atleta."""

        raw = update.get("update_id")

        return str(raw) if raw is not None else None

    @staticmethod
    def is_from_bot(message: dict) -> bool:

        return bool(
            (message.get("from") or {}).get("is_bot")
        )

    @staticmethod
    def chat_id(message: dict) -> str | None:

        chat = message.get("chat") or {}

        chat_id = chat.get("id")

        return str(chat_id) if chat_id is not None else None

    @staticmethod
    def sender_name(message: dict) -> str:

        sender = message.get("from") or {}

        return sender.get("first_name") or ""

    @staticmethod
    def extract_text(message: dict) -> str | None:

        # legenda de mídia também conta como texto
        return message.get("text") or message.get("caption")

    @staticmethod
    def extract_media(message: dict) -> dict | None:
        """Foto (maior resolução) ou documento suportado ->
        {file_id, mimetype, caption}."""

        photos = message.get("photo")

        if photos:

            # o Telegram manda várias resoluções; a última é a maior
            largest = photos[-1]

            return {
                "file_id": largest["file_id"],
                "mimetype": PHOTO_MIMETYPE,
                "caption": message.get("caption") or "",
            }

        document = message.get("document")

        if document:

            mimetype = document.get("mime_type", "")

            if mimetype in SUPPORTED_MEDIA_MIMETYPES:

                return {
                    "file_id": document["file_id"],
                    "mimetype": mimetype,
                    "caption": message.get("caption") or "",
                }

        return None
