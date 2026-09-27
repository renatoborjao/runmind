"""Mensagem de MÍDIA pro coach (foto/PDF ou áudio), igual em qualquer canal
(app ou Telegram). A mídia vira TEXTO que o coach entende — áudio pela
transcrição local, foto pela leitura da IA — e segue pelo MESMO pipeline da
conversa (CoachConversationEvent): decide/executa/aprende com o histórico
completo do atleta. Nada de caminho paralelo.

Exceção única: atleta com treinador externo mandando a PLANILHA do treinador →
leitura de plano (ExternalPlanEvent), como sempre foi.

Falha nunca vira silêncio: sempre sai uma resposta honesta.
"""

from __future__ import annotations

from app.application.coach.media.image_reader import InboundImageReader
from app.application.events.coach_conversation import CoachConversationEvent
from app.application.events.external_plan_received import ExternalPlanEvent
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.config import get_settings
from app.infrastructure.integrations.audio.voice_transcriber import (
    VoiceTranscriber,
)
from app.infrastructure.persistence.chat_media_store import ChatMediaStore
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)

PDF_MIMETYPE = "application/pdf"

_KIND_LABEL = {
    "training_plan": "planilha de treino",
    "workout": "registro de treino/prova",
    "other": "imagem",
}

UNOPENABLE_IMAGE_REPLY = (
    "Não consegui abrir essa imagem. 😕 Tenta mandar de novo (ou um print "
    "da tela)?"
)

UNSEEN_IMAGE_REPLY = (
    "Recebi sua foto, mas não consegui enxergar direito agora. 😕 Me conta "
    "em uma frase o que ela mostra que eu te ajudo?"
)

VOICE_TOO_LONG_REPLY = (
    "Esse áudio ficou longo demais pra eu ouvir com atenção. 🙉 "
    "Manda um mais curtinho ou me escreve que eu te respondo."
)

VOICE_FAILED_REPLY = (
    "Tentei ouvir seu áudio mas não consegui agora. 😕 "
    "Pode repetir ou me mandar por escrito?"
)

VOICE_UNHEARD_REPLY = (
    "Não consegui te ouvir direito nesse áudio. 🙉 "
    "Repete pra mim ou escreve?"
)


def compose_image_text(reading: dict, caption: str) -> str:
    """O que o coach LÊ: a legenda do atleta (se houver) + o que a foto mostra."""

    label = _KIND_LABEL.get(reading.get("kind"), "imagem")

    note = f"[📷 Foto enviada pelo atleta — {label}: {reading['description']}]"

    return f"{caption}\n\n{note}" if caption else note


class CoachMediaMessage:

    @staticmethod
    async def image(
        profile: str,
        raw: bytes,
        mimetype: str,
        caption: str = "",
        notify: bool = True,
    ) -> str:
        """Foto/PDF do atleta -> resposta do coach. `notify=False` no app (a
        resposta vai pra tela); no Telegram o coach responde pelo canal."""

        runner = LoadRunnerProfile.execute(profile)

        caption = (caption or "").strip()

        is_pdf = (mimetype or "").lower() == PDF_MIMETYPE

        attachment = None

        content = raw

        if not is_pdf:

            try:

                media_id, content = ChatMediaStore().save_image(profile, raw)

            except ValueError:

                return await CoachMediaMessage._reply_only(
                    runner, profile, "📷 (imagem que não abriu)", caption,
                    None, UNOPENABLE_IMAGE_REPLY, notify,
                )

            mimetype = "image/jpeg"

            attachment = {"type": "image", "id": media_id}

        reading = await InboundImageReader.read(content, mimetype, caption)

        # treinador externo + planilha (ou PDF, ou leitura falhou: era o
        # comportamento de sempre) -> registra o plano do treinador
        if runner.external_coach and (
            is_pdf or reading is None or reading["kind"] == "training_plan"
        ):

            reply = await ExternalPlanEvent.execute(
                profile,
                media_bytes=content,
                mimetype=mimetype,
                notify=notify,
            )

            coach_text = "📷 [Atleta mandou a planilha do treinador]"

            if caption:

                coach_text = f"{caption}\n\n{coach_text}"

            CoachMediaMessage._record(
                profile, coach_text, caption, attachment, reply,
            )

            return reply

        if reading is None:

            if caption:

                # a legenda ainda dá conversa: segue com ela (e avisa a IA)
                return await CoachConversationEvent.execute(
                    profile=profile,
                    incoming_text=(
                        f"{caption}\n\n[📷 O atleta mandou uma foto junto, "
                        "mas ela não pôde ser lida.]"
                    ),
                    notify=notify,
                    display_text=caption,
                    attachment=attachment,
                )

            return await CoachMediaMessage._reply_only(
                runner, profile, "📷 [foto que não pôde ser lida]", caption,
                attachment, UNSEEN_IMAGE_REPLY, notify,
            )

        return await CoachConversationEvent.execute(
            profile=profile,
            incoming_text=compose_image_text(reading, caption),
            notify=notify,
            display_text=caption,
            attachment=attachment,
        )

    @staticmethod
    async def voice(
        profile: str,
        raw: bytes,
        duration_seconds: float | None = None,
        notify: bool = True,
    ) -> dict:
        """Áudio do atleta -> {"transcript", "reply"}. `transcript` None quando
        não deu pra ouvir (aí `reply` é o aviso honesto, que não vai pro
        histórico — é só um "repete?")."""

        if duration_seconds and duration_seconds > get_settings().voice_max_seconds:

            return {"transcript": None, "reply": VOICE_TOO_LONG_REPLY}

        try:

            text = await VoiceTranscriber.transcribe(raw)

        except Exception as e:

            print(f"Falha ao transcrever áudio do app de '{profile}': {e}")

            return {"transcript": None, "reply": VOICE_FAILED_REPLY}

        if not text:

            return {"transcript": None, "reply": VOICE_UNHEARD_REPLY}

        print(f"Voz transcrita (app {profile}): {text!r}")

        reply = await CoachConversationEvent.execute(
            profile=profile,
            incoming_text=text,
            notify=notify,
            display_text=f"🎤 {text}",
        )

        return {"transcript": text, "reply": reply}

    # ------------------------------------------------------------------

    @staticmethod
    def _record(
        profile: str,
        coach_text: str,
        caption: str,
        attachment: dict | None,
        reply: str,
    ) -> None:
        """Guarda o par na conversa (o atleta volta nele depois, no app ou no
        chat) — conversa viva."""

        repo = ConversationRepository()

        repo.append_turn(
            profile,
            role="user",
            text=coach_text,
            display_text=caption,
            attachment=attachment,
        )

        repo.append_turn(profile, role="assistant", text=reply)

    @staticmethod
    async def _reply_only(
        runner,
        profile: str,
        coach_text: str,
        caption: str,
        attachment: dict | None,
        reply: str,
        notify: bool,
    ) -> str:

        CoachMediaMessage._record(
            profile, coach_text, caption, attachment, reply,
        )

        if notify:

            await NotificationService.send(runner, reply)

        return reply
