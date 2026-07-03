# Formatos aceitos para plano de treinador (print/foto/PDF).
SUPPORTED_MEDIA_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


class WhatsAppInboundParser:

    @staticmethod
    def extract_text(
        data: dict,
    ) -> str | None:

        message = data.get("message") or {}

        if "conversation" in message:

            return message["conversation"]

        extended = message.get("extendedTextMessage")

        if extended and "text" in extended:

            return extended["text"]

        return None

    @staticmethod
    def extract_media(
        data: dict,
    ) -> dict | None:
        """Imagem ou documento suportado na mensagem:
        {key_id, mimetype, caption} — senão None."""

        message = data.get("message") or {}

        media = (
            message.get("imageMessage")
            or message.get("documentMessage")
        )

        if not media:

            return None

        mimetype = media.get("mimetype", "")

        # mimetype pode vir com sufixo (ex: "image/jpeg; codecs=...")
        if mimetype.split(";")[0] not in SUPPORTED_MEDIA_MIMETYPES:

            return None

        key_id = (data.get("key") or {}).get("id")

        if not key_id:

            return None

        return {
            "key_id": key_id,
            "mimetype": mimetype.split(";")[0],
            "caption": media.get("caption") or "",
        }

    @staticmethod
    def is_group_message(
        remote_jid: str,
    ) -> bool:

        # Grupos usam sufixo "@g.us"; listas de transmissão usam
        # "@broadcast". Conversas diretas usam "@s.whatsapp.net" (ou o
        # sufixo "@lid" no modo de endereçamento por LID). O coach só
        # deve responder a conversas diretas, nunca a grupos.
        return remote_jid.endswith("@g.us") or remote_jid.endswith(
            "@broadcast",
        )
