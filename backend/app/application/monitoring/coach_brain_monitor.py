"""Vigia da SAÚDE do cérebro do coach (observabilidade ativa).

Com o cérebro no ar pra todos, ele às vezes devolve None e a conversa cai na
cascata determinística (fallback). Um fallback isolado é normal (blip de JSON,
indecisão); uma TAXA ALTA e sustentada de fallback é sinal de que o cérebro
está degradando — mesmo com o Gemini de pé — e ninguém veria isso até um print
ruim aparecer. Este vigia mede a taxa numa janela rolante e avisa o dono no
Telegram quando ela estoura (1x por episódio), e avisa de novo quando normaliza.

Diferente do [[project_gemini_alias_thinking_bug]]/AIHealthMonitor (que conta
FALHAS DURAS seguidas do Gemini): aqui o sinal é o cérebro PUNTAR (None) com
frequência, que pode acontecer mesmo com o Gemini funcionando. Complementa, não
substitui. Best-effort: nada aqui pode derrubar a resposta ao atleta.
"""

from app.application.notifications.notification_service import (
    TELEGRAM,
    NotificationService,
)
from app.core.config import get_settings
from app.infrastructure.persistence.coach_brain_health_repository import (
    CoachBrainHealthRepository,
)

# tamanho da janela rolante (últimos N desfechos do cérebro). Grande o bastante
# pra não oscilar com um blip; pequena o bastante pra reagir no mesmo dia.
WINDOW = 30

# só avalia com a janela cheia (amostra mínima) — evita alarme com 2-3 mensagens
MIN_SAMPLE = WINDOW

# taxa de fallback que dispara o alerta (40% dos últimos 30 = claramente anômalo;
# em operação normal o cérebro punta pouquíssimo)
HIGH_RATE = 0.40

# taxa que considera normalizado (histerese: não fica ligando/desligando na borda)
LOW_RATE = 0.15


class CoachBrainMonitor:

    @staticmethod
    async def record(fallback: bool) -> None:
        """Registra um desfecho do cérebro (fallback=True quando devolveu None)
        e alerta/recupera conforme a taxa da janela. Best-effort — engole tudo,
        nunca propaga."""

        try:

            repo = CoachBrainHealthRepository()

            state = repo.load()

            window = list(state.get("window", []))[-(WINDOW - 1):]

            window.append(1 if fallback else 0)

            alerted = bool(state.get("alerted", False))

            rate = sum(window) / len(window) if window else 0.0

            full = len(window) >= MIN_SAMPLE

            should_alert = full and rate >= HIGH_RATE and not alerted

            recovered = alerted and full and rate <= LOW_RATE

            repo.save(
                {
                    "window": window,
                    "alerted": (alerted or should_alert) and not recovered,
                }
            )

            if should_alert:

                pct = round(rate * 100)

                await CoachBrainMonitor._notify(
                    f"⚠️ Ritmind: o cérebro do coach caiu no fallback em ~{pct}% "
                    f"das últimas {len(window)} mensagens. Sinal de degradação "
                    f"(prompt/JSON/indecisão) mesmo com o Gemini de pé. Olhe o "
                    f"/debug/brain/{{perfil}}; se preciso, kill switch "
                    f"COACH_BRAIN_ENABLED=false."
                )

            elif recovered:

                await CoachBrainMonitor._notify(
                    "✅ Ritmind: a taxa de fallback do cérebro do coach "
                    "normalizou."
                )

        except Exception as e:  # noqa: BLE001 — vigia é best-effort

            print(f"Vigia do cérebro falhou: {e}")

    @staticmethod
    async def _notify(message: str) -> None:
        """Alerta pro dono. Sem admin configurado = silêncio (feature off).
        Falha no envio nunca propaga."""

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

            print(f"Falha ao enviar alerta do cérebro: {e}")
