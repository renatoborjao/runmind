import json
from pathlib import Path


class ProcessedInboundGuard:
    """Idempotência dos webhooks de MENSAGEM (Telegram/WhatsApp): garante
    que cada mensagem recebida seja processada UMA única vez, mesmo que o
    canal reentregue o mesmo update (retry porque o ack demorou, ou
    redelivery após o servidor voltar).

    Sem isso, uma instabilidade momentânea do Gemini virava enxurrada de
    "me embananei": cada reentrega rodava o pipeline do zero e mandava um
    fallback novo pro atleta. É o oposto de um coach confiável.

    A chave é uma string namespaceada pelo canal ("tg:<update_id>",
    "wac:<wamid>", "wa:<message_id>") pra ids de canais diferentes nunca
    colidirem. Persistido em arquivo pra sobreviver a restart.

    storage/processed_inbound.json — lista das últimas N chaves vistas.
    """

    # nº máximo de chaves guardadas: a reentrega sempre chega logo após a
    # mensagem original, então uma janela curta já cobre; evita o arquivo
    # crescer sem fim.
    MAX_KEYS = 1000

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

        self.file = self.storage / "processed_inbound.json"

    def _load(self) -> list[str]:

        if not self.file.exists():

            return []

        with open(
            self.file,
            encoding="utf-8",
        ) as f:

            return json.load(f)

    def _save(
        self,
        keys: list[str],
    ) -> None:

        with open(
            self.file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(keys, f)

    def check_and_mark(
        self,
        key: str,
    ) -> bool:
        """True se a mensagem é nova (marca e libera o processamento);
        False se já foi vista (chamador deve ignorar).

        Síncrono e sem await: a leitura e a escrita acontecem sem ceder o
        event loop, então duas entregas concorrentes não passam ambas.
        """

        keys = self._load()

        if key in keys:

            return False

        keys.append(key)

        self._save(keys[-self.MAX_KEYS:])

        return True
