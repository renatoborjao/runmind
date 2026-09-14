"""Espelho no APP dos toques PROATIVOS do coach: a mesma mensagem que sai no
Telegram também vira uma notificação DENTRO do app (central com sino/badge) e um
Web Push no celular. Enquanto nem todo atleta migrou pro app, ninguém depende de
um canal só — o Telegram continua saindo igual, e o app recebe em paralelo.

É chamado nos PONTOS PROATIVOS (CoachOutbox e os poucos envios diretos), nunca
nas respostas reativas do chat (ali o atleta já está na conversa). Best-effort:
falhar aqui jamais derruba a mensagem que já saiu no canal."""

from __future__ import annotations

import asyncio

from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.telegram.telegram_text import to_plain_text
from app.infrastructure.notifications.web_push_sender import WebPushSender
from app.infrastructure.persistence.app_notification_repository import (
    AppNotificationRepository,
)

# kind -> título amigável do card/push. Kind desconhecido cai num título neutro.
_TITLES = {
    "feedback": "Análise do seu treino",
    "race_debrief": "Debrief da prova",
    "personal_record": "Recorde! 🏅",
    "race_day": "É dia de prova! 🏁",
    "race_eve": "Véspera de prova",
    "race_journey": "Sua jornada até a prova",
    "race_week": "Semana de prova",
    "race_taper": "Reta final (taper)",
    "announcement": "Novidade no Ritmind",
    "morning_briefing": "Bom dia — seu dia",
    "daily_training": "Seu treino de hoje",
    "weekly_review": "Sua semana",
    "weekly_plan": "Seu plano da semana",
    "wellbeing_followup": "Como você está?",
    "reengagement": "Senti sua falta 👋",
    "goal_projection": "Rumo à sua meta",
    "monthly_recap": "Seu mês",
    "pace_progress": "Sua evolução de pace",
    "cadence_progress": "Sua evolução de cadência",
    "state_portrait": "Seu retrato de hoje",
    "strava_connect": "Plano atualizado",
    "external_plan": "Treino recebido",
    "wear_alert": "Seus tênis",
    "watch_update": "Enviar pro relógio",
}

_DEFAULT_TITLE = "Mensagem do coach"

# tamanho do corpo do push (o card no app mostra o texto inteiro)
_PUSH_BODY_MAX = 140


def _title_for(kind: str | None) -> str:

    if not kind:

        return _DEFAULT_TITLE

    return _TITLES.get(kind, _DEFAULT_TITLE)


def _push_body(message: str) -> str:

    plain = to_plain_text(message or "").strip()

    if len(plain) <= _PUSH_BODY_MAX:

        return plain

    return plain[: _PUSH_BODY_MAX - 1].rstrip() + "…"


class AppInbox:

    @staticmethod
    async def deliver(
        runner: RunnerProfile,
        message: str,
        kind: str | None = None,
    ) -> None:
        """Registra a notificação na central do app e dispara o Web Push. A chave
        do atleta é `runner.id` (== chave do login). Nunca levanta."""

        profile = runner.id

        if not profile:

            return

        title = _title_for(kind)

        # 1) central do app (feed com estado lido/não-lido)
        try:

            AppNotificationRepository().append(
                profile,
                text=to_plain_text(message),
                title=title,
                kind=kind,
            )

        except Exception as e:

            print(f"[app_inbox] falha ao registrar p/ '{profile}': {e}")

        # 2) Web Push (celular buzina mesmo com o app fechado) — em thread, pra
        #    a rede do push não travar o event loop; best-effort
        try:

            await asyncio.to_thread(
                WebPushSender.send,
                profile,
                title,
                _push_body(message),
                "/inicio",
            )

        except Exception as e:

            print(f"[app_inbox] falha no push p/ '{profile}': {e}")
