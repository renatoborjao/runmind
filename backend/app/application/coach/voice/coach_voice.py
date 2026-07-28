"""O coach FALANDO: emenda uma nota de ÁUDIO à mensagem (o texto já sai por
outro caminho — CoachOutbox). Usado só nos BEATS que emocionam (dia da prova,
véspera, recorde, debrief). O áudio é sempre best-effort — se a síntese ou o
envio falharem, o texto já saiu e o atleta nunca fica no silêncio (conversa
viva). Hoje só o Telegram tem bolha de voz; outros canais recebem só o texto.
Ver [[project_ideias_produto]]."""

import re

from app.application.notifications.notification_service import TELEGRAM
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.audio.speech_synthesizer import (
    SpeechSynthesizer,
)
from app.infrastructure.integrations.telegram.telegram_service import (
    TelegramService,
)
from app.infrastructure.integrations.telegram.telegram_text import (
    to_plain_text,
)

# emojis/símbolos que a voz não deve tentar "ler" (edge lê texto, não
# figurinha). Cobre os blocos de emoji + setas/dingbats + o seletor de
# variação.
_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "←-⇿"
    "⬀-⯿"
    "️"
    "]",
    flags=re.UNICODE,
)


class CoachVoice:

    @staticmethod
    async def voice_only(runner: RunnerProfile, text: str) -> None:
        """Só a parte de ÁUDIO — o texto já foi (ou será) enviado por outro
        caminho (ex.: CoachOutbox, que também registra no outbox). Best-effort."""

        # bolha de voz só existe no Telegram por enquanto
        if runner.channel != TELEGRAM or not runner.telegram_id:

            return

        try:

            audio = await SpeechSynthesizer.synthesize(
                CoachVoice._speakable(text),
            )

            if audio is None:

                return

            await TelegramService.send_voice(runner.telegram_id, audio)

        except Exception as e:

            print(f"Voz do coach falhou p/ {runner.telegram_id}: {e}")

    @staticmethod
    def _speakable(text: str) -> str:
        """Texto pronto pra fala: sem markdown, sem emoji, bullets viram
        pausa. Assim a voz sai limpa em vez de 'asterisco', 'bullet' etc."""

        clean = to_plain_text(text)

        clean = _EMOJI.sub("", clean)

        # bullet vira vírgula (pausa natural quando falado)
        clean = clean.replace("•", ",")

        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\n{2,}", "\n", clean)

        return clean.strip()
