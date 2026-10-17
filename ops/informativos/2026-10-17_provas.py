"""Informativo: Provas no app — várias provas, com papel (principal/preparatória/de treino).

RASCUNHO — aguarda aprovação do Renato. Por padrão só MOSTRA a mensagem e quem
receberia (dry-run). Pra enviar de verdade: `python 2026-10-17_provas.py --send`.

Roda NA VM (como o da nutrição): copiar pra ~/ e rodar com o python do .venv.
Canal de cada atleta + central do app + push, via CoachOutbox (sem `kind` =
anúncio, o governador não suprime)."""

import asyncio
import sys

sys.path.insert(0, "/home/ubuntu/runmind/backend")

from app.application.notifications.coach_outbox import CoachOutbox  # noqa: E402
from app.infrastructure.persistence.runner_profile_repository import (  # noqa: E402
    RunnerProfileRepository,
)

MESSAGE = (
    "🏁 Novidade no app: suas provas, do jeito certo\n"
    "\n"
    "Agora o Ritmind enxerga TODAS as suas provas — não só a mais próxima — e "
    "monta o seu ciclo de treino olhando o calendário inteiro.\n"
    "\n"
    "COMO FUNCIONA\n"
    "1) No app, abra Perfil → Minhas provas.\n"
    "2) Cadastre cada prova: nome, data e, se quiser, o tempo-alvo. A "
    "distância eu descubro pelo nome (\"10 km\", \"meia maratona\") — ou você "
    "informa.\n"
    "3) Escolha o PAPEL de cada uma:\n"
    "• Principal — o grande alvo. Seu plano se organiza rumo a ela: pico de "
    "treino e polimento completo.\n"
    "• Preparatória — um marco no caminho (ex.: uma 15 km no meio do ciclo "
    "da meia). Eu miro a meta dela e uso como teste de forma, mas só com um "
    "mini-polimento, sem reorganizar o ciclo.\n"
    "• De treino — entra como um treino (longão ritmado ou qualidade), sem "
    "polimento.\n"
    "Se você não escolher, eu sugiro (a mais longa vira a principal) e você "
    "confirma com um toque.\n"
    "\n"
    "TAMBÉM PELA CONVERSA\n"
    "Pode me contar aqui mesmo: \"a meia é minha principal e a de 15 km é só "
    "um degrau\", \"adiaram a prova pro dia 10/01\" ou \"cancelaram a "
    "prova\". Eu atualizo a sua lista.\n"
    "\n"
    "📅 As mudanças valem a partir do próximo domingo — a semana que está "
    "rolando não vira de cabeça pra baixo.\n"
    "\n"
    "Ainda não tem o app? Me manda \"quero o app\" que eu te envio o link. 👊"
)

RECIPIENTS = ["fernanda", "helio", "joaosoares", "leonardo", "mauricio", "renato2"]


async def main(send: bool):

    repo = RunnerProfileRepository()

    if not send:

        print("DRY-RUN (nada enviado). Use --send pra enviar.\n")
        print(MESSAGE)
        print()

    for pid in RECIPIENTS:

        try:

            runner = repo.load(pid)

            if not send:

                print(f"receberia: {pid} ({runner.name}) via {runner.channel}")

                continue

            await CoachOutbox.send(runner, MESSAGE, profile=pid)

            print(f"OK   {pid} ({runner.name}) via {runner.channel}")

        except Exception as e:

            print(f"FALHA {pid}: {e}")


asyncio.run(main("--send" in sys.argv))
