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
