"""ARQUIVO PERMANENTE — nada do atleta se perde.

Vários repositórios guardam só uma JANELA (as últimas 200 mensagens, 60 dias de diário, 10 mensagens
enviadas, 26 leituras do corpo, as 300 análises mais recentes...) e apagavam o resto: o coach de hoje
não sabia de onde o atleta veio. Renato (01/11): "todo o histórico nós devemos guardar e não perder
nada — com isso o coach analisa e monta o plano; uma semana ruim ou dias ruins não deveriam matar o
plano e a evolução do atleta".

Aqui o que sai da janela vai pra `storage/archive/<tipo>/<perfil>.jsonl` (uma linha por registro,
só se acrescenta, nunca se reescreve nem se apaga). A janela de trabalho continua do mesmo tamanho:
o prompt do coach não cresce. Duas garantias:

- só sai da janela o que FOI arquivado: se gravar o arquivo falhar, a janela fica inteira
  (melhor um arquivo maior que um registro perdido);
- registro SUBSTITUÍDO (releitura do mesmo dia, plano refeito) também entra: a versão que o
  coach jogou fora é justamente o que ele precisa pra aprender com a própria decisão.

O `storage/` inteiro já entra no backup, então o arquivo vai junto."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

NEWLINE = chr(10)


class PermanentArchive:

    @staticmethod
    def file(storage: Path, kind: str, profile: str) -> Path:
        """`storage` = a pasta do próprio repositório (storage/<tipo>/): o arquivo mora ao lado,
        em storage/archive/<tipo>/. Quem troca `storage` (teste) leva o arquivo junto."""

        return Path(storage).parent / "archive" / kind / f"{profile}.jsonl"

    @staticmethod
    def append(
        storage: Path, kind: str, profile: str, records: list, reason: str,
    ) -> bool:
        """Acrescenta os registros. True se TUDO foi gravado (ou não havia nada); False em qualquer
        falha — e então quem chamou NÃO pode apagar o original."""

        if not records:

            return True

        try:

            path = PermanentArchive.file(storage, kind, profile)

            path.parent.mkdir(parents=True, exist_ok=True)

            stamp = datetime.now(UTC).isoformat()

            lines = "".join(
                json.dumps(
                    {"archived_at": stamp, "reason": reason, "record": record},
                    ensure_ascii=False,
                    default=str,
                )
                + NEWLINE
                for record in records
            )

            with open(path, "a", encoding="utf-8") as f:

                f.write(lines)

            return True

        except Exception as e:  # noqa: BLE001 — falhar aqui nunca derruba o fluxo do atleta

            print(f"Arquivo permanente falhou p/ '{profile}' ({kind}): {e}")

            return False

    @staticmethod
    def trim_list(
        storage: Path,
        kind: str,
        profile: str,
        items: list,
        keep: int,
        *,
        serialize: Callable | None = None,
        newest_first: bool = False,
        reason: str = "saiu da janela",
    ) -> list:
        """Mantém `keep` itens na janela e arquiva o excedente (os mais ANTIGOS: o começo da lista,
        ou o fim se `newest_first`). Devolve a janela. Se o arquivamento falhar, devolve a lista
        INTEIRA — nada é apagado."""

        if len(items) <= keep:

            return items

        if newest_first:

            window, dropped = items[:keep], items[keep:]

        else:

            window, dropped = items[len(items) - keep:], items[: len(items) - keep]

        records = [serialize(item) if serialize else item for item in dropped]

        if PermanentArchive.append(storage, kind, profile, records, reason):

            return window

        return items

    @staticmethod
    def trim_dict(
        storage: Path,
        kind: str,
        profile: str,
        data: dict,
        keep: int,
        *,
        date_key: str = "date",
        reason: str = "saiu da janela",
    ) -> dict:
        """O mesmo para um dicionário `{id: registro}`: fica com os `keep` mais recentes por
        `date_key`; o resto vai pro arquivo como `{"key": id, "value": registro}`."""

        if len(data) <= keep:

            return data

        ordered = sorted(
            data.items(), key=lambda kv: (kv[1] or {}).get(date_key, ""), reverse=True,
        )

        window, dropped = ordered[:keep], ordered[keep:]

        records = [{"key": key, "value": value} for key, value in dropped]

        if PermanentArchive.append(storage, kind, profile, records, reason):

            return dict(window)

        return data

    @staticmethod
    def load(storage: Path, kind: str, profile: str) -> list[dict]:
        """Os registros arquivados, na ordem em que entraram, cada um como
        `{"archived_at", "reason", "record"}`. Linha ilegível é pulada. Vazio sem arquivo."""

        path = PermanentArchive.file(storage, kind, profile)

        if not path.exists():

            return []

        out = []

        try:

            with open(path, encoding="utf-8") as f:

                for line in f:

                    try:

                        out.append(json.loads(line))

                    except json.JSONDecodeError:

                        continue

        except OSError:

            return []

        return out
