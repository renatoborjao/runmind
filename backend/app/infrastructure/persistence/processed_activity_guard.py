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

    # quantas vezes uma MESMA atividade pode voltar pra fila depois de falhar. Cada
    # tentativa repete a análise paga (Gemini): sem teto, uma falha depois da IA
    # (ex.: envio da mensagem) reanalisa a cada passada do poller — Hélio, noite de
    # 06/11: 340 análises em 8 h.
    MAX_RETRIES = 3

    def release_for_retry(self, activity_id: int) -> bool:
        """Solta a marca pra o poller tentar de novo, MAS só até `MAX_RETRIES`
        vezes por atividade. Devolve True se soltou; False se desistiu (a marca
        fica — não analisa mais, o erro está no log pra investigar)."""

        counts_file = self.storage / "analysis_retries.json"

        try:

            counts = json.loads(counts_file.read_text(encoding="utf-8"))

        except Exception:

            counts = {}

        key = str(activity_id)

        tries = int(counts.get(key, 0)) + 1

        counts[key] = tries

        # só os mais recentes: o arquivo não cresce sem fim
        counts = dict(list(counts.items())[-self.MAX_IDS:])

        counts_file.write_text(json.dumps(counts), encoding="utf-8")

        if tries > self.MAX_RETRIES:

            print(
                f"Atividade {activity_id}: {tries - 1} tentativas falharam — "
                "desisti (não reanalisa pra não queimar IA); ver o erro acima"
            )

            return False

        self.unmark(activity_id)

        return True
