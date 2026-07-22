"""Alerta proativo de saúde da IA: quando o coach falha VÁRIAS vezes
seguidas ao responder atletas (Gemini fora, parâmetro rejeitado, cota
estourada...), avisa o DONO no Telegram na hora — em vez de a falha morrer
no log até alguém descobrir por acaso testando (foi assim que o bug do
thinking_budget=0 foi achado, ver [[project_gemini_alias_thinking_bug]]).

NÃO previne a quebra (dependência externa sempre pode mudar) — encurta o
tempo cego entre quebrar e o Renato saber. Um sucesso zera o contador e, se
já tinha alertado, avisa que voltou ao normal.

Regras de projeto:
- só alerta 1x por episódio (não spama a cada falha subsequente);
- alerta desligado se admin_telegram_id vazio (nunca envia à toa);
- falha no PRÓPRIO alerta nunca derruba o fluxo de resposta ao atleta.
"""

from app.application.notifications.notification_service import (
    NotificationService,
    TELEGRAM,
)
from app.core.config import get_settings
from app.infrastructure.persistence.ai_health_repository import (
    AIHealthRepository,
)

# falhas seguidas pra disparar o alerta. 3 filtra o blip isolado (uma
# instabilidade de 1 mensagem já tem retry adiado no webhook) e pega o
# problema sustentado.
FAILURE_THRESHOLD = 3


class AIHealthMonitor:

    @staticmethod
    async def record_success() -> None:
        """Coach respondeu de verdade (via Gemini). Zera o contador; se
        estávamos em estado alertado, avisa que voltou ao normal."""

        repo = AIHealthRepository()

        state = repo.load()

        if state.get("consecutive_failures", 0) == 0 and not state.get(
            "alerted"
        ):

            return

        was_alerted = state.get("alerted", False)

        repo.save({"consecutive_failures": 0, "alerted": False})

        if was_alerted:

            await AIHealthMonitor._notify(
                "✅ RunMind: o coach voltou a responder normalmente."
            )

    @staticmethod
    async def record_failure(reason: str) -> None:
        """Coach caiu no fallback ('me embananei') porque a IA falhou. Conta;
        ao cruzar o limiar pela 1ª vez, alerta o dono com a causa."""

        repo = AIHealthRepository()

        state = repo.load()

        failures = state.get("consecutive_failures", 0) + 1

        already_alerted = state.get("alerted", False)

        should_alert = failures >= FAILURE_THRESHOLD and not already_alerted

        repo.save(
            {
                "consecutive_failures": failures,
                "alerted": already_alerted or should_alert,
            }
        )

        if should_alert:

            await AIHealthMonitor._notify(
                f"⚠️ RunMind: o coach falhou {failures} vezes seguidas ao "
                f"responder atletas. Última causa: {reason[:300]}\n\n"
                f"Verifique o backend/Gemini."
            )

    @staticmethod
    async def _notify(message: str) -> None:
        """Manda o alerta pro dono. Sem admin configurado = silêncio (feature
        off). Falha no envio nunca propaga — alerta é best-effort."""

        admin_id = get_settings().admin_telegram_id

        if not admin_id:

            return

        try:

            await NotificationService.send_to(
                channel=TELEGRAM,
                address=admin_id,
                message=message,
            )

        except Exception as e:  # noqa: BLE001 — alerta best-effort

            print(f"Falha ao enviar alerta de saúde da IA: {e}")
