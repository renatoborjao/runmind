"""A proposta de mudança de plano que o coach fez e o atleta ainda não respondeu — descrita do
mesmo jeito pra TODAS as vozes (mensagem da proposta, dossiê do plano/bom dia/análise/chat).

Antes só o chat via a proposta, e ela caducava em silêncio em 24 h: o coach sugeria "longão de
12 km em vez de 16" no sábado e, no domingo, o bom dia celebrava os 16 km e a análise cobrava o
corte (Fernanda 14-15/11); ou dizia "reorganizei os dias, posso aplicar?" sem dizer o quê
(Hélio 15/11). Puro: recebe a proposta e a hora, não lê storage."""

from datetime import datetime, timedelta

from app.core.weekdays import weekday_label

# a proposta vale o "sim" por este tempo (o mesmo de ProposalFlow)
OPEN_HOURS = 24

# depois de caducar sem resposta, as vozes ainda sabem dela por este tempo
UNANSWERED_HOURS = 72

OPEN = "open"

UNANSWERED = "unanswered"


def _get(obj, key):

    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def age(proposal, now: datetime) -> timedelta | None:

    try:

        created = datetime.fromisoformat(str(_get(proposal, "created_at")))

    except (TypeError, ValueError):

        return None

    if created.tzinfo is None and now.tzinfo is not None:

        created = created.replace(tzinfo=now.tzinfo)

    return now - created


def status(proposal, now: datetime) -> str | None:
    """OPEN (ainda vale o sim), UNANSWERED (caducou sem resposta, há pouco) ou None."""

    if proposal is None:

        return None

    elapsed = age(proposal, now)

    if elapsed is None:

        return None

    if elapsed <= timedelta(hours=OPEN_HOURS):

        return OPEN

    if elapsed <= timedelta(hours=UNANSWERED_HOURS):

        return UNANSWERED

    return None


def _size(session: dict) -> str:

    km = session.get("planned_distance_km")

    if km:

        return f"{float(km):.1f}".replace(".0", "").replace(".", ",") + " km"

    minutes = session.get("planned_duration_minutes")

    return f"{minutes} min" if minutes else ""


def describe_operations(operations) -> list[str]:
    """Cada mudança em português de corredor: 'domingo: Longão 12 km' / 'quarta: sai do plano'."""

    lines = []

    for op in operations or []:

        if not isinstance(op, dict):

            continue

        day = weekday_label(str(op.get("day") or "")) or str(op.get("day") or "")

        if op.get("action") == "drop":

            lines.append(f"{day}: sai do plano (descanso)")

            continue

        session = op.get("session") or {}

        what = " ".join(x for x in (session.get("workout_type") or "treino", _size(session)) if x)

        lines.append(f"{day}: {what}")

    return lines


def message_with_changes(message: str, operations) -> str:
    """A mensagem da proposta + o que muda, concreto, pro atleta poder decidir."""

    changes = describe_operations(operations)

    if not changes:

        return message

    return (
        message.rstrip()
        + "\n\n👉 O que muda, se você topar:\n"
        + "\n".join(f"• {line}" for line in changes)
        + "\nResponde *sim* que eu ajusto (ou *não* pra manter como está)."
    )


def dossier_lines(proposal, now: datetime) -> list[str]:
    """O que as outras vozes precisam saber da proposta (vazio se não há ou já passou)."""

    state = status(proposal, now)

    if state is None:

        return []

    elapsed = age(proposal, now)

    try:

        created = datetime.fromisoformat(str(_get(proposal, "created_at")))

        when = f"{created:%d/%m %H:%M}"

    except (TypeError, ValueError):

        when = "há pouco"

    changes = "; ".join(describe_operations(_get(proposal, "operations"))) or "(sem detalhe)"

    week = str(_get(proposal, "week_start") or "")

    if len(week) == 10:

        changes = f"para a semana de {week[8:10]}/{week[5:7]} — {changes}"

    preview = " ".join(str(_get(proposal, "preview") or "").split())[:300]

    if state == OPEN:

        left = max(0, OPEN_HOURS - int(elapsed.total_seconds() // 3600))

        return [
            f"PROPOSTA EM ABERTO (você propôs em {when}; vale o 'sim' por mais ~{left} h): "
            f"{changes}. O que você disse: \"{preview}\". O plano gravado AINDA é o antigo. Se "
            "falar com ele antes da resposta, NÃO contradiga a proposta nem fale do plano antigo "
            "como se nada tivesse sido sugerido: lembre a proposta em 1 linha (ele responde sim/"
            "não) ou siga o assunto sem decidir por ele."
        ]

    return [
        f"PROPOSTA SEM RESPOSTA (você propôs em {when} e ele não respondeu; caducou e o plano "
        f"seguiu o antigo): {changes}. O que você disse: \"{preview}\". Não celebre nem cobre o "
        "treino antigo como se você não tivesse sugerido mudar: reconheça a sugestão (\"eu "
        "tinha sugerido X; como ficou o original, …\") e julgue a decisão dele sem culpa."
    ]
