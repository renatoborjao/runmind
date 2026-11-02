"""RECONSTRUÇÃO DE CONVERSAS A PARTIR DO LOG DE DECISÕES — o que nenhum backup guardou.

Renato (01/11): "guarde todas as conversas dos atletas e faça com que o coach sempre tenha visibilidade".
As conversas de agosto a meados de setembro do Renato e do Maurício saíram da janela de 200 turnas antes
de existir o arquivo permanente (nº 91) e nenhum backup as guardou. Mas o log de decisões do cérebro do
coach registrou, para CADA mensagem, o texto do atleta (`incoming`) e um trecho da resposta (`say`), os
dois cortados em 200 caracteres. Não é a conversa inteira, é a fala dele de volta — o bastante pra o
coach (e a busca da lembrança da conversa) saberem o que foi pedido, combinado e respondido.

Aqui as entradas do log viram turnas no mesmo formato da conversa, marcadas `reconstructed`, e só entram
as que a conversa viva e o arquivo NÃO têm (dedupe pelo dia e pelo começo do texto). Rodar de novo não
duplica. Puro/determinístico; o script `ops/rebuild_conversations.py` grava no arquivo permanente."""

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

# quantos caracteres do começo do texto identificam a mensagem
_PREFIX = 50


def _norm(text: str) -> str:

    lowered = (text or "").lower()

    plain = "".join(
        c for c in unicodedata.normalize("NFD", lowered) if unicodedata.category(c) != "Mn"
    )

    return re.sub(r"\s+", " ", plain).strip()[:_PREFIX]


def _utc(stamp) -> datetime | None:

    try:

        moment = datetime.fromisoformat(str(stamp))

    except ValueError:

        return None

    if moment.tzinfo is None:

        return moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc)


def known_keys(turns: list[dict]) -> set[tuple[date, str]]:
    """O que a conversa já tem: (dia UTC, começo do texto normalizado) das falas do ATLETA."""

    keys = set()

    for turn in turns:

        if turn.get("role") != "user":

            continue

        moment = _utc(turn.get("timestamp"))

        if moment is None:

            continue

        # áudio e foto: `text` é a transcrição/descrição que o coach lê (o que o log registra) e
        # `display_text` é o que o app mostra — a mesma fala pode estar em qualquer um dos dois
        for field in ("text", "display_text"):

            value = turn.get(field) or ""

            if value.strip():

                keys.add((moment.date(), _norm(value)))

    return keys


def reconstruct(brain_entries: list[dict], known_turns: list[dict]) -> list[dict]:
    """As turnas que FALTAM, em ordem cronológica: a fala do atleta e o trecho da resposta do coach,
    de cada entrada do log cuja mensagem a conversa não tem. Cada turna: `role`, `text`, `timestamp`
    (UTC) e `reconstructed: True`."""

    seen = known_keys(known_turns)

    out: list[dict] = []

    for entry in sorted(brain_entries, key=lambda e: str(e.get("ts"))):

        incoming = (entry.get("incoming") or "").strip()

        moment = _utc(entry.get("ts"))

        if not incoming or moment is None:

            continue

        key = _norm(incoming)

        # o horário do log é local (-03:00) e o da conversa é UTC: o mesmo instante pode cair em
        # dias diferentes, então vale o dia anterior e o seguinte também
        if any((moment.date() + timedelta(days=shift), key) in seen for shift in (-1, 0, 1)):

            continue

        out.append({
            "role": "user",
            "text": incoming,
            "timestamp": moment.isoformat(),
            "reconstructed": True,
        })

        say = (entry.get("say") or "").strip()

        if say:

            out.append({
                "role": "assistant",
                "text": say,
                "timestamp": (moment + timedelta(seconds=1)).isoformat(),
                "reconstructed": True,
            })

    return out


def rebuild_profile(profile: str, *, apply: bool = False) -> int:
    """Quantas turnas faltavam na conversa (vivas + arquivo) deste atleta e foram (ou seriam)
    gravadas no arquivo permanente. Sem `apply` só conta."""

    from app.infrastructure.persistence.coach_brain_log_repository import CoachBrainLogRepository
    from app.infrastructure.persistence.conversation_repository import ConversationRepository
    from app.infrastructure.persistence.permanent_archive import PermanentArchive

    brain = CoachBrainLogRepository()

    conversations = ConversationRepository()

    entries = brain.load(profile) + [
        e["record"] for e in PermanentArchive.load(brain.storage, "coach_brain_log", profile)
    ]

    known = conversations.load(profile) + [
        e["record"] for e in PermanentArchive.load(conversations.storage, "conversations", profile)
    ]

    missing = reconstruct(entries, known)

    if apply and missing:

        PermanentArchive.append(
            conversations.storage, "conversations", profile, missing,
            "reconstruído do log de decisões (fala do atleta e trecho da resposta, até 200 caracteres)",
        )

    return len(missing)
