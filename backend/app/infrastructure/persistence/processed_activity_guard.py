import json
from pathlib import Path


class ProcessedActivityGuard:
    """Idempotência do webhook do Strava: garante que cada atividade
    gere feedback UMA única vez, mesmo que o Strava reentregue o mesmo
    evento (retry porque o ack passou de ~2s, ou redelivery após o
    servidor voltar). Persistido em arquivo pra sobreviver a restart.

    storage/processed_activities.json — lista dos últimos N ids vistos.
    """

    # nº máximo de ids guardados: a reentrega sempre chega logo após o
    # evento original, então uma janela curta já cobre; evita o arquivo
    # crescer sem fim.
    MAX_IDS = 500

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.file = self.storage / "processed_activities.json"

    def _load(self) -> list[int]:

        if not self.file.exists():

            return []

        with open(
            self.file,
            encoding="utf-8",
        ) as f:

            return json.load(f)

    def _save(
        self,
        ids: list[int],
    ) -> None:

        with open(
            self.file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(ids, f)

    def check_and_mark(
        self,
        activity_id: int,
    ) -> bool:
        """True se a atividade é nova (marca e libera o processamento);
        False se já foi processada (chamador deve ignorar).

        Síncrono e sem await: a leitura e a escrita acontecem sem ceder
        o event loop, então duas entregas concorrentes não passam ambas.
        """

        ids = self._load()

        if activity_id in ids:

            return False

        ids.append(activity_id)

        self._save(ids[-self.MAX_IDS:])

        return True

    def is_marked(
        self,
        activity_id: int,
    ) -> bool:
        """Consulta sem efeito colateral — usada pelo delete pra saber
        se essa atividade chegou a ser processada (e portanto se o
        atleta recebeu feedback que precisa de retratação)."""

        return activity_id in self._load()

    def unmark(
        self,
        activity_id: int,
    ) -> None:
        """Remove a marca — usado quando o processamento falhou, pra
        uma reentrega legítima poder tentar de novo."""

        ids = [
            i
            for i in self._load()
            if i != activity_id
        ]

        self._save(ids)
