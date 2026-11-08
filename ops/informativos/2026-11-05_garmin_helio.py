"""Informativo: Garmin do Hélio conectado (aprovado pelo Renato em 05/11).

Dry-run por padrão; `--send` envia de verdade. Só o Hélio recebe."""

import asyncio
import sys

sys.path.insert(0, "/home/ubuntu/runmind/backend")

from app.application.notifications.coach_outbox import CoachOutbox  # noqa: E402
from app.infrastructure.persistence.runner_profile_repository import (  # noqa: E402
    RunnerProfileRepository,
)

MESSAGE = (
    "⌚ Hélio, seu relógio Garmin agora está conectado ao Ritmind\n"
    "\n"
    "Parabéns pelo relógio novo! A partir de agora:\n"
    "\n"
    "• Seus treinos vão pro relógio. Já enviei o de sábado, o Longão de "
    "12,5 km. É o maior treino que você já fez, e o importante é segurar o "
    "ritmo (6:25 a 6:50 por km).\n"
    "\n"
    "• Como dar o play: sincronize o relógio com o app Garmin Connect no "
    "celular. No sábado, abra Corrida, vá em Treinos → Programado, escolha "
    "Longão Base e inicie. O relógio mostra o ritmo-alvo enquanto você corre.\n"
    "\n"
    "• Suas corridas passam a ser lidas pelo relógio, com batimentos e ritmo "
    "mais certinhos que o GPS do celular. A análise de cada treino fica mais "
    "precisa.\n"
    "\n"
    "• Eu passo a acompanhar seu corpo: sono e recuperação, pra ajustar o "
    "plano quando você estiver cansado.\n"
    "\n"
    "Depois de cada corrida, deixe o relógio sincronizar com o Garmin "
    "Connect. Os treinos de antes, que vieram do celular, continuam no seu "
    "histórico. Qualquer dúvida, é só falar aqui. Bons treinos! 🏃"
)

RECIPIENTS = ["helio"]


async def main(send: bool):

    repo = RunnerProfileRepository()

    for pid in RECIPIENTS:

        runner = repo.load(pid)

        if not send:

            print(f"DRY-RUN: {pid} ({runner.name}) via {runner.channel}\n")
            print(MESSAGE)

            continue

        await CoachOutbox.send(runner, MESSAGE, profile=pid)

        print(f"OK   {pid} ({runner.name}) via {runner.channel}")


asyncio.run(main("--send" in sys.argv))
