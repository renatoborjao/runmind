"""Reconstrói, no ARQUIVO PERMANENTE, as conversas que a janela de 200 turnas já cortou, a partir do log
de decisões do coach (fala do atleta + trecho da resposta). Só ACRESCENTA; rodar de novo não duplica.

  cd ~/runmind/backend && .venv/bin/python /tmp/rebuild_conversations.py            # só conta
  cd ~/runmind/backend && .venv/bin/python /tmp/rebuild_conversations.py --apply    # grava
"""
import sys

sys.path.insert(0, ".")

from app.application.history.conversation_rebuild import rebuild_profile
from app.infrastructure.persistence.runner_profile_repository import RunnerProfileRepository

apply = "--apply" in sys.argv

total = 0

for profile in RunnerProfileRepository().list_active():

    count = rebuild_profile(profile, apply=apply)

    total += count

    print(f"{profile:<12} +{count} turnas" + (" (gravado)" if apply and count else ""))

print("TOTAL", total, "(aplicado)" if apply else "(só conferência)")
