"""Informativo aprovado pelo Renato (27/09): coach com um cérebro só +
percepção (autoavaliação do Garmin / contar como sentiu). Canal de cada atleta +
central do app + push, via CoachOutbox (sem `kind` = anúncio, o governador não
suprime). A linha do Garmin só vai pra quem tem relógio conectado."""

import asyncio
import sys

sys.path.insert(0, "/home/ubuntu/runmind/backend")

from app.application.notifications.coach_outbox import CoachOutbox  # noqa: E402
from app.infrastructure.integrations.garmin.garmin_client import GarminClient  # noqa: E402
from app.infrastructure.persistence.runner_profile_repository import (  # noqa: E402
    RunnerProfileRepository,
)

HEAD = (
    "🏃 Novidade no teu coach\n"
    "\n"
    "Agora ele junta tudo que sabe de você — treinos, corpo, sono, o que você "
    "sente e o que já te falou — num lugar só. Isso vale igual pro plano, pra "
    "análise do treino, pro bom dia e pra nossa conversa.\n"
    "\n"
    "E ele quer saber como VOCÊ sente os treinos:\n"
)

GARMIN = (
    "• Liga a Autoavaliação no teu Garmin (Corrida → Configurações → "
    "Autoavaliação). No fim da corrida o relógio pergunta esforço e sensação, "
    "e eu leio sozinho — nem precisa me responder.\n"
)

TALK = (
    "• Ou só me conta do teu jeito: \"foi tranquilo\", \"perna pesada no "
    "fim\", \"morri no longão\".\n"
)

TAIL = (
    "\n"
    "Quanto mais eu souber como você sente, mais certeira fica a tua semana. 👊"
)

RECIPIENTS = ["fernanda", "helio", "joaosoares", "leonardo", "mauricio", "renato2"]


async def main():

    repo = RunnerProfileRepository()

    for pid in RECIPIENTS:

        try:

            runner = repo.load(pid)

            garmin = GarminClient.is_connected(pid)

            message = HEAD + (GARMIN if garmin else "") + (
                TALK if garmin else TALK.replace("• Ou só", "• É só")
            ) + TAIL

            await CoachOutbox.send(runner, message, profile=pid)

            print(f"OK   {pid} ({runner.name}) via {runner.channel} garmin={garmin}")

        except Exception as e:

            print(f"FALHA {pid}: {e}")


asyncio.run(main())
