SUPPORTED_MEDIA_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


class WhatsAppCloudInboundParser:
    """Lê o payload do webhook da Cloud API (Graph). O formato é aninhado:
    entry[].changes[].value.messages[]. Só conversa direta com texto ou
    mídia suportada interessa — status (entregue/lido) e o resto é
    ignorado pelo chamador."""

    @staticmethod
    def first_message(
        payload: dict,
    ) -> dict | None:
        """A primeira mensagem de usuário do payload (a Meta manda uma por
        vez no uso normal), já com o value do change junto pra pegar o
        nome do contato. Retorna {message, value} ou None."""

        for entry in payload.get("entry", []):

            for change in entry.get("changes", []):

                value = change.get("value") or {}

                messages = value.get("messages")

                if not messages:

                    continue

                return {"message": messages[0], "value": value}

        return None

    @staticmethod
    def sender_phone(
        message: dict,
    ) -> str | None:

        return message.get("from")

    @staticmethod
    def sender_name(
        value: dict,
    ) -> str:

        contacts = value.get("contacts") or []

        if contacts:

            return (contacts[0].get("profile") or {}).get("name", "")

        return ""

    @staticmethod
    def extract_text(
        message: dict,
    ) -> str | None:

        if message.get("type") == "text":

            return (message.get("text") or {}).get("body")

        # imagem/documento com legenda: a legenda é a intenção do atleta
        media = message.get(message.get("type"))

        if isinstance(media, dict) and media.get("caption"):

            return media["caption"]

        return None

    @staticmethod
    def extract_media(
        message: dict,
    ) -> dict | None:
        """Imagem ou documento suportado: {media_id, mimetype, caption}.
        media_id é baixado depois via Graph (WhatsAppCloudMediaClient)."""

        msg_type = message.get("type")

        if msg_type not in ("image", "document"):

            return None

        media = message.get(msg_type) or {}

        mimetype = (media.get("mime_type") or "").split(";")[0]

        if mimetype not in SUPPORTED_MEDIA_MIMETYPES:

            return None

        media_id = media.get("id")

        if not media_id:

            return None

        return {
            "media_id": media_id,
            "mimetype": mimetype,
            "caption": media.get("caption") or "",
        }
