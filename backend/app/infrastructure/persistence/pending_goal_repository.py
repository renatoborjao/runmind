import json
from datetime import datetime
from pathlib import Path

from app.core.clock import now_local

# Só honra o estado por uma janela curta: se o atleta disse "quero trocar
# meu objetivo" e some por horas, a resposta seguinte a uma pergunta ANTIGA
# não deve ser tratada como a meta nova (evita sequestrar mensagem à toa).
PENDING_TTL_MINUTES = 20


class PendingGoalRepository:
    """Marca que o coach perguntou 'qual é a meta agora?' e está esperando a
    resposta. Enquanto pendente, a próxima mensagem do atleta é lida como o
    novo objetivo — mesmo sem a palavra-gatilho (objetivo/meta/prova). Um
    arquivinho por atleta, no máximo um pendente, com validade curta."""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "pending_goal"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def mark(self, profile: str) -> None:
        """Arma o estado: a partir de agora a próxima resposta é a meta."""

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(
                {"at": now_local().isoformat()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def is_pending(self, profile: str) -> bool:
        """True se há uma pergunta de objetivo aberta e ainda dentro da
        janela de validade. Estado caduco é limpo na hora."""

        file = self._file(profile)

        if not file.exists():

            return False

        try:

            with open(file, encoding="utf-8") as f:

                at = datetime.fromisoformat(json.load(f)["at"])

        except (json.JSONDecodeError, KeyError, ValueError, TypeError):

            self.clear(profile)

            return False

        age_minutes = (now_local() - at).total_seconds() / 60

        if age_minutes > PENDING_TTL_MINUTES:

            self.clear(profile)

            return False

        return True

    def clear(self, profile: str) -> None:
        """Some com o estado pendente (consumido ou caducado)."""

        file = self._file(profile)

        if file.exists():

            file.unlink()
