"""Vigia de prontidão — a ponta que OBSERVA sempre e, atrás de flag, FALA.

Roda no mesmo momento matinal do BodyConductNotifier (09h local), pra ser UMA
voz de manhã, não três. Sempre avalia + grava o diário (observação); só ENVIA
quando `readiness_alerts_enabled` está ligada. Cobre só a LACUNA do ajuste de
corpo: CAUTION (recuperação pedindo atenção num dia puxado) e GREEN (sinal
verde num dia puxado). A sobrecarga real (STRAINED/BRAKE) continua no
BodyConductNotifier, que propõe mudar o plano — aqui não duplicamos.

O texto é determinístico (custo zero, previsível). Dá pra trocar por Gemini
depois, quando o Renato aprovar os alertas no diário. Ver
[[project_analise_corpo_garmin]]."""

from app.application.coach.intelligence.readiness_service import (
    ReadinessService,
)
from app.application.notifications.coach_outbox import CoachOutbox
from app.core.config import get_settings
from app.domain.entities.readiness_verdict import (
    READINESS_CAUTION,
    READINESS_GREEN,
    ReadinessVerdict,
)
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.dispatch_guard import DispatchGuard

_ALERT_TIERS = frozenset({READINESS_CAUTION, READINESS_GREEN})


class ReadinessNotifier:

    @staticmethod
    async def observe_and_maybe_alert(
        profile: str,
        runner: RunnerProfile,
    ) -> None:

        # avalia + grava o diário SEMPRE (observação) — isto é o gate do Renato
        verdict, entry = await ReadinessService.evaluate(profile)

        # daqui pra baixo é ENVIO — só com a flag ligada
        if not get_settings().readiness_alerts_enabled:

            return

        # só a lacuna (CAUTION/GREEN) e só quando o estado VIROU (would_notify)
        if verdict.tier not in _ALERT_TIERS or not entry.would_notify:

            return

        # 1x por (dia, estado) — dedup extra por cima da mudança de estado
        period = f"{entry.day}:{verdict.tier}"

        if DispatchGuard.already_sent("readiness_alert", profile, period):

            return

        message = ReadinessNotifier._message(verdict)

        await CoachOutbox.send(runner, message)

        DispatchGuard.mark("readiness_alert", profile, period)

    @staticmethod
    def _message(verdict: ReadinessVerdict) -> str:

        if verdict.tier == READINESS_CAUTION:

            foco = f" (principalmente {verdict.limiter})" if verdict.limiter else ""

            return (
                "Oi! Dei uma olhada no seu corpo hoje e a recuperação está "
                f"pedindo atenção{foco}. O treino de hoje é dos puxados — se "
                "sentir que não rende, pode pegar leve sem culpa. Recuperar "
                "bem agora é o que sustenta a evolução. 💪"
            )

        # GREEN
        return (
            "Bom dia! Seu corpo está recuperado e com espaço pra puxar. Se "
            "hoje é dia de treino forte, pode ir com confiança — o momento "
            "está a favor. 🚀"
        )
