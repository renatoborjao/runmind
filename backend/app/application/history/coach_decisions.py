"""AS DECISÕES DO COACH COM ESTE ATLETA — o que ele pediu e o que o coach fez, o histórico todo.

O log de decisões do cérebro do coach (uma entrada por mensagem: o que o atleta escreveu, o que foi
decidido, se era resposta a uma proposta) ficava guardado e ninguém o lia ao montar o plano. Renato
(01/11): "o log de decisões do coach está guardado mas ainda não é lido — precisa já ter a visão para os
próximos planos". O plano nasce, então, sabendo o que esse atleta costuma PEDIR: o dia que sempre troca,
o treino que sempre pula, quantas vezes pediu mais volume, quantas propostas aceitou ou recusou.

Lê o log vivo E o arquivo permanente, o histórico inteiro. DADO + conhecimento, nunca regra: pedido
repetido diz da rotina e da preferência real; pedido isolado (clima, viagem, agenda do dia) não faz
padrão ([[feedback_ia_decide_sem_regras]], [[feedback_base_historico_sempre]]). Puro/determinístico."""

from collections import Counter
from datetime import date, datetime, timedelta

# ações do cérebro que NÃO mudam o plano de treino (tênis, envio pro relógio) ficam fora da conta
_IGNORED = frozenset({"shoe", "watch"})

_TYPE_PT = {
    "move": "troca de dia",
    "skip": "treino pulado a pedido",
    "adjust": "ajuste de treino",
    "simplify": "treino simplificado",
    "routine": "rotina de dias/horário",
    "goal": "meta/objetivo",
    "one_off": "treino avulso",
    "replan": "semana refeita",
    "days": "dias de treino da semana",
    "preference": "preferência registrada",
    "coach_switch": "troca de treinador",
}

# resposta de uma palavra a uma proposta: a decisão já aparece no pedido que a gerou
_BARE_CONFIRMATIONS = frozenset({"sim", "s", "ok", "isso", "pode", "pode ser", "blz", "beleza", "claro", "yes"})

# mensagem do próprio coach repassada pelo atleta (o plano da semana colado de volta)
_ECHO_STARTS = ("🏃", "🩺", "📅", "🗓", "Ritmind")

_DAY_PT = {
    "monday": "segunda", "tuesday": "terça", "wednesday": "quarta", "thursday": "quinta",
    "friday": "sexta", "saturday": "sábado", "sunday": "domingo",
}

_PENDING_PT = {
    "accept": "aceitou", "confirm": "aceitou", "approved": "aceitou",
    "reject": "recusou", "refine": "pediu ajuste na proposta",
}

RECENT_WEEKS = 8

LAST_DECISIONS = 8

_ASK_CHARS = 90


def actions_of(entry: dict) -> list[dict]:
    """As ações de uma entrada, nos dois formatos que o log já teve (`actions` lista; `action` único),
    sem as que não mexem no treino."""

    raw = entry.get("actions")

    if not isinstance(raw, list):

        raw = [entry["action"]] if isinstance(entry.get("action"), dict) else []

    return [a for a in raw if isinstance(a, dict) and a.get("type") and a["type"] not in _IGNORED]


def _day(stamp) -> date | None:

    try:

        return datetime.fromisoformat(str(stamp)).date()

    except ValueError:

        return None


def _clip(text: str, limit: int) -> str:

    text = " ".join((text or "").split())

    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _is_a_request(text) -> bool:
    """Pedido de verdade: não é um "sim" solto nem o plano do coach colado de volta."""

    clean = " ".join((text or "").lower().split()).strip(" .!?")

    return bool(clean) and clean not in _BARE_CONFIRMATIONS and not (text or "").lstrip().startswith(_ECHO_STARTS)


def _describe(action: dict) -> str:

    label = _TYPE_PT.get(action["type"], action["type"])

    target = _DAY_PT.get(str(action.get("target_day") or "").lower())

    detail = action.get("content_change")

    text = label + (f" ({target})" if target else "")

    return text + (f": {_clip(detail, 60)}" if detail else "")


def render(entries: list[dict], today: date) -> str:
    """O bloco pro prompt, do log inteiro (`entries` de qualquer ordem). Vazio sem decisão que mude
    o treino nem proposta respondida."""

    ordered = sorted(
        (e for e in entries if _day(e.get("ts")) is not None), key=lambda e: str(e.get("ts")),
    )

    if not ordered:

        return ""

    first = _day(ordered[0]["ts"])

    since = today - timedelta(weeks=RECENT_WEEKS)

    total, recent = Counter(), Counter()

    days: Counter = Counter()

    decisions = []

    for entry in ordered:

        found = actions_of(entry)

        for action in found:

            total[action["type"]] += 1

            if _day(entry["ts"]) >= since:

                recent[action["type"]] += 1

            if action["type"] in ("move", "skip") and action.get("target_day"):

                days[(action["type"], str(action["target_day"]).lower())] += 1

        if found and _is_a_request(entry.get("incoming")):

            decisions.append((entry, found))

    proposals = Counter(
        _PENDING_PT[e["on_pending"]] for e in ordered if e.get("on_pending") in _PENDING_PT
    )

    if not total and not proposals:

        return ""

    lines = [
        f"SUAS DECISÕES COM ELE (o log do cérebro do coach, {len(ordered)} mensagens tratadas desde "
        f"{first:%d/%m/%y}; o que ele PEDIU e o que você fez):"
    ]

    def counts(counter: Counter) -> str:

        return ", ".join(
            f"{n} {_TYPE_PT.get(kind, kind)}" for kind, n in counter.most_common()
        )

    if total:

        lines.append(f"- No histórico todo: {counts(total)}.")

    if recent:

        lines.append(f"- Nas últimas {RECENT_WEEKS} semanas: {counts(recent)}.")

    for kind, label in (("move", "Dia para onde ele mais passa o treino"), ("skip", "Dias que ele mais pula")):

        top = [(d, n) for (k, d), n in days.most_common() if k == kind][:3]

        if top:

            lines.append(
                f"- {label}: " + ", ".join(f"{_DAY_PT.get(d, d)} ({n}x)" for d, n in top) + "."
            )

    if proposals:

        lines.append(
            "- Propostas que você fez: " + ", ".join(f"{n}x {what}" for what, n in proposals.most_common()) + "."
        )

    if decisions:

        lines.append(f"- Últimos pedidos que mudaram o plano (do mais antigo ao mais novo):")

        for entry, found in decisions[-LAST_DECISIONS:]:

            ask = _clip(entry.get("incoming") or "", _ASK_CHARS)

            lines.append(
                f"  - {_day(entry['ts']):%d/%m} ele disse \"{ask}\" → " + "; ".join(_describe(a) for a in found)
            )

    lines.append(
        "CONHECIMENTO, não regra: é o histórico dos PEDIDOS dele e do que você fez. Pedido que se repete "
        "(o mesmo dia sempre trocado, o mesmo treino sempre pulado, mais volume no longão) diz da rotina e "
        "da preferência real dele — leve isso pra semana sem esperar ele pedir de novo. Um pedido isolado, "
        "feito por clima, viagem ou agenda do dia, não faz padrão nem muda a preferência."
    )

    return "\n".join(lines)


def for_profile(profile: str, today: date) -> str:
    """O bloco do atleta a partir do storage (log vivo + arquivo permanente). Best-effort: em qualquer
    falha devolve vazio e o resto do dossiê segue."""

    try:

        from app.infrastructure.persistence.coach_brain_log_repository import (
            CoachBrainLogRepository,
        )
        from app.infrastructure.persistence.permanent_archive import PermanentArchive

        brain = CoachBrainLogRepository()

        entries = brain.load(profile) + [
            e["record"] for e in PermanentArchive.load(brain.storage, "coach_brain_log", profile)
        ]

        return render(entries, today)

    except Exception as e:  # noqa: BLE001 — a visão das decisões nunca derruba o dossiê

        print(f"Decisões do coach falharam p/ '{profile}': {e}")

        return ""
