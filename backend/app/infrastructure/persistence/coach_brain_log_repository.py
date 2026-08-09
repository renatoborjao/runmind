"""Log de decisões do cérebro do coach — storage/coach_brain_log/{profile}.json.

Modo observação: com o cérebro no ar pra todos, registra O QUE ele decidiu por
mensagem (ação/escopo/dia/cartão/pendência + trecho da fala), pra dar pra
acompanhar semana a semana e pegar deriva ANTES de virar print ruim. Série
ordenada com teto, gitignored (dado de atleta). Lido via GET /debug/brain/{p}.
Ver [[project_roteador_acao_ia]]."""

import json
from pathlib import Path

# janela recente basta — o valor está em ver o padrão dos últimos dias
_MAX = 200


class CoachBrainLogRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "coach_brain_log"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def load(self, profile: str) -> list[dict]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError, TypeError):

            return []

    def record(self, profile: str, entry: dict) -> None:
        """Anexa um registro de decisão. Best-effort: falhar aqui NUNCA pode
        derrubar a conversa — o chamador engole a exceção."""

        entries = self.load(profile)

        entries.append(entry)

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(entries[-_MAX:], f, ensure_ascii=False, indent=2)
