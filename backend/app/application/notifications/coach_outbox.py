"""Envia uma mensagem AUTOMÁTICA do coach (análise pós-treino, briefing, plano
da semana, review) E a registra no outbox — pra o coach lembrar do que disse
quando o atleta comentar depois no chat. O chat normal já grava seus próprios
turnos (user/assistant); este outbox é só pras mensagens de FORA do fluxo de
conversa, que não entrariam no histórico."""

from app.application.coach.voice.coach_voice import CoachVoice
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.notifications.proactive_governor import ProactiveGovernor
from app.core.config import get_settings
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.telegram.telegram_text import (
    to_plain_text,
)
from app.infrastructure.persistence.coach_outbox_repository import (
    CoachOutboxRepository,
)
from app.infrastructure.persistence.voice_preference_repository import (
    VoicePreferenceRepository,
)


class CoachOutbox:

    @staticmethod
    async def send(
        runner: RunnerProfile,
        message: str,
        voice: bool = False,
        profile: str | None = None,
        kind: str | None = None,
    ) -> None:
        """Envia a mensagem automática do coach e registra no outbox. Com
        `voice=True` (beats emocionais: dia da prova, recorde, bom dia),
        emenda uma nota de ÁUDIO — best-effort e só se o atleta não tiver
        pedido só texto. `profile` é a chave da preferência de voz.

        `kind` (ex.: "morning_briefing", "reengagement") liga o GOVERNADOR de
        proativos: com a flag ligada pro perfil, o portão decide se pode sair
        (teto diário + isenção dos essenciais + dedup). Sem `kind` ou flag OFF,
        segue igual a hoje. Ver [[ProactiveGovernor]]."""

        governed = bool(kind) and profile is not None and (
            get_settings().proactive_governor_active_for(profile)
        )

        if governed:

            ok, reason = ProactiveGovernor.admit(
                profile, kind, message, get_settings().proactive_daily_budget,
            )

            if not ok:

                print(f"[governador] {kind} suprimido p/ '{profile}': {reason}")

                return

        await NotificationService.send(runner, message)

        # áudio proativo: best-effort, respeita a preferência dinâmica
        if voice and (
            profile is None
            or VoicePreferenceRepository.wants_audio(profile)
        ):

            await CoachVoice.voice_only(runner, message)

        # registrar no outbox NUNCA pode derrubar o envio já feito
        try:

            CoachOutboxRepository().append(
                runner.id,
                to_plain_text(message),
            )

        except Exception as e:

            print(
                f"Falha ao registrar mensagem do coach ({runner.id}): {e}"
            )

        # diário do governador (só quando ele está atuando pro perfil): registra
        # o envio pra o teto/dedup do dia enxergarem este toque
        if governed:

            ProactiveGovernor.record(profile, kind, message)
