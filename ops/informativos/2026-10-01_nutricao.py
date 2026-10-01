"""Informativo: Nutrição no app (plano alimentar a partir da bioimpedância).

RASCUNHO — aguarda aprovação do Renato. Por padrão só MOSTRA a mensagem e quem
receberia (dry-run). Pra enviar de verdade: `python 2026-10-01_nutricao.py --send`.

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
    "🥗 Novidade no app: Nutrição\n"
    "\n"
    "Agora o Ritmind monta um plano alimentar pra você, a partir da sua "
    "bioimpedância e do seu plano de treino.\n"
    "\n"
    "COMO FUNCIONA\n"
    "1) No app, abra Nutrição (card na tela inicial).\n"
    "2) Registre sua bioimpedância: tire uma foto do laudo (eu leio os "
    "números) ou digite na mão. Só o peso é obrigatório — quanto mais dados, "
    "mais certeiro.\n"
    "3) Escolha o que você quer: perder gordura, ganhar massa, performance "
    "ou manter. Dá pra juntar até 3 (ex.: perder gordura + ganhar massa). Se "
    "quiser, informe o peso que quer atingir e eu estimo em quantas semanas.\n"
    "4) Pronto: o plano sai na hora.\n"
    "\n"
    "O QUE VEM NO PLANO\n"
    "• Metas de calorias e macros ligadas ao seu treino: dia de descanso, dia "
    "de treino e longão têm metas diferentes.\n"
    "• Cardápio no formato de plano de nutricionista: pré-treino, café, "
    "almoço, lanche, jantar (e ceia, se quiser), com porções, opções de "
    "troca (\"ou\") e substituições.\n"
    "• Treinos longos: o que comer antes, durante (carbo por hora conforme a "
    "duração) e depois.\n"
    "• Ajustes pro dia de descanso e pra véspera do longão, mais orientações "
    "gerais.\n"
    "• Dá pra baixar tudo em PDF.\n"
    "\n"
    "📅 UMA VEZ POR MÊS\n"
    "A bioimpedância e o plano atualizam 1 vez por mês — vale igual se você "
    "enviar a foto ou digitar os dados. Ao registrar a nova medição, o plano "
    "é refeito na hora e você revisa seu objetivo e peso-alvo junto. No app "
    "aparece a data em que a próxima atualização libera.\n"
    "\n"
    "⚠️ IMPORTANTE\n"
    "Os cálculos e o cardápio são feitos por inteligência artificial e são "
    "ESTIMATIVAS — não substituem um nutricionista. Se você tem alguma "
    "condição de saúde, alergia ou necessidade específica, procure um "
    "profissional.\n"
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
