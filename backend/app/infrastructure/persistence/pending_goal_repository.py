import json
from datetime import datetime
from pathlib import Path

from app.core.clock import now_local

# Janela do fluxo REATIVO: o atleta disse "quero trocar meu objetivo" e o
# coach perguntou "qual?". A resposta vem em SEGUIDA; se some por horas, a
# mensagem seguinte a uma pergunta ANTIGA não deve virar a meta nova (evita
# sequestrar mensagem à toa).
PENDING_TTL_MINUTES = 20

# Janela do fluxo PROATIVO: FOMOS nós que perguntamos (broadcast "confirma teu
# objetivo"). O atleta responde quando puder — horas ou dias depois — e a
# devolutiva NÃO PODE se perder. Por isso a validade é longa. Ver
# [[project_reconciliacao_coach]].
PROACTIVE_GOAL_TTL_MINUTES = 14 * 24 * 60


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

    def mark(
        self,
        profile: str,
        ttl_minutes: int = PENDING_TTL_MINUTES,
    ) -> None:
        """Arma o estado: a partir de agora a próxima resposta é a meta. O
        `ttl_minutes` viaja GRAVADO com a marca — reativo usa o padrão curto;
        o broadcast proativo passa `PROACTIVE_GOAL_TTL_MINUTES` (a devolutiva
        pode chegar dias depois)."""

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(
                {
                    "at": now_local().isoformat(),
                    "ttl_minutes": ttl_minutes,
                },
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

                data = json.load(f)

            at = datetime.fromisoformat(data["at"])

            # dado legado (sem ttl gravado) cai no padrão curto reativo
            ttl_minutes = int(data.get("ttl_minutes", PENDING_TTL_MINUTES))

        except (json.JSONDecodeError, KeyError, ValueError, TypeError):

            self.clear(profile)

            return False

        age_minutes = (now_local() - at).total_seconds() / 60

        if age_minutes > ttl_minutes:

            self.clear(profile)

            return False

        return True

    def clear(self, profile: str) -> None:
        """Some com o estado pendente (consumido ou caducado)."""

        file = self._file(profile)

        if file.exists():

            file.unlink()
