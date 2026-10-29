"""FORTE PRESCRITO × FORTE ENTREGUE — correr no dia certo não é entregar o estímulo.

O coach prescrevia um treino forte em TODA semana do Leonardo (fartlek, progressivo, tempo run,
ritmo de prova, limiar, VO2) e o sistema contava cada um como "feito" porque ele corria naquele
dia. Só que ele fazia todos em ritmo de leve: ritmo de prova com alvo 6:00-6:15 saiu a 7:14;
limiar com alvo 6:15-6:25 a 6:51; VO2 com alvo 5:40-5:55 a 6:37 — esforço percebido 3/10 em todos.
O balanço de estímulos dizia "limiar: fez 2", o aviso da auditoria dizia só "0% do tempo em zona
forte" (sem quantas semanas, sem a causa), e o coach seguia prescrevendo outro forte igual (21/10,
29/10).

Aqui sai o que faltava: por sessão forte feita, se ele ENTREGOU o estímulo — pelos blocos do
relógio quando há (ritmo dentro da faixa), senão pelo esforço que ele mesmo relatou — e há quantas
semanas não entrega um. É DADO + CONHECIMENTO pro coach tratar a CAUSA (alvo acima do que ele
sustenta, ele não empurra, terreno), nunca cota nem fórmula ([[feedback_ia_decide_sem_regras]]).
Puro/determinístico."""

from dataclasses import dataclass
from datetime import date, timedelta

from app.application.history.execution_log import ExecutionLog
from app.application.history.stimulus_ledger import (
    FARTLEK,
    HILLS,
    PROGRESSION,
    RACE_PACE,
    THRESHOLD,
    VO2,
)
from app.domain.entities.workout_step import INTERVAL, RUN

# sessões que existem pra carregar o estímulo forte
QUALITY = {RACE_PACE, HILLS, FARTLEK, THRESHOLD, VO2, PROGRESSION}

WINDOW_WEEKS = 6

# bateu a faixa em pelo menos esta fração dos blocos medidos = entregou
_DELIVERED_SHARE = 0.6

# sem blocos medidos, o que ele mesmo sentiu decide: até 3/10 num treino forte é leve; 5+ é forte
_SOFT_RPE = 3
_HARD_RPE = 5

DELIVERED = "entregou"
SOFT = "sem intensidade"
UNKNOWN = "sem medida"

_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


@dataclass(slots=True)
class Delivery:

    day: date
    workout_type: str
    verdict: str
    detail: str
    gap_s: int | None = None
    rpe: int | None = None


@dataclass(slots=True)
class DeliverySummary:

    prescribed: int
    done: int
    delivered: int
    soft: int
    unknown: int
    last_delivered: date | None
    weeks_without: int | None
    mean_gap_s: int | None
    mean_rpe: float | None
    items: list[Delivery]


def _gap_seconds(pace: str | None, target: str | None) -> int | None:
    """Quantos s/km o ritmo ficou da faixa: positivo = mais lento que a ponta lenta, negativo = mais
    rápido que a ponta rápida, 0 = dentro."""

    executed = ExecutionLog._sec(pace)

    fast, _, slow = (target or "").partition("-")

    fast_s, slow_s = ExecutionLog._sec(fast), ExecutionLog._sec(slow)

    if None in (executed, fast_s, slow_s):

        return None

    fast_s, slow_s = min(fast_s, slow_s), max(fast_s, slow_s)

    if executed > slow_s:

        return executed - slow_s

    if executed < fast_s:

        return executed - fast_s

    return 0


_TREADMILL_WORDS = ("esteira", "treadmill")


def _treadmill_named(text: str | None) -> bool:

    return any(word in (text or "").lower() for word in _TREADMILL_WORDS)


def _indoor(act) -> bool:
    """Corrida na esteira: a marca do relógio ou o nome da gravação."""

    return bool((getattr(act, "raw", None) or {}).get("trainer")) or _treadmill_named(
        getattr(act, "name", None)
    )


def _blocks(entry: dict | None) -> list[dict]:
    """Os blocos de estímulo MEDIDOS (com a faixa do passo e se bateu)."""

    return [
        b for b in (entry or {}).get("blocks") or []
        if b.get("kind") in (RUN, INTERVAL) and b.get("ok") is not None and b.get("target")
    ]


def judge(
    session, act, entry: dict | None, rpe: int | None, day: date, indoor: bool = False,
) -> Delivery:
    """Uma sessão forte FEITA: entregou o estímulo? `indoor`: outros sinais de esteira (outra
    gravação do dia com "esteira" no nome, ou ele escreveu "esteira" na nota)."""

    name = session.workout_type

    blocks = _blocks(entry)

    if blocks:

        told = ", relato dele na esteira" if (entry or {}).get("reported") else ""

        gaps = [_gap_seconds(b.get("pace"), b.get("target")) for b in blocks]

        # bateu a faixa OU correu mais rápido que ela: o estímulo chegou (mais rápido é pacing, não
        # leveza — Leonardo no fartlek de 02/10: tiros a 5:17-5:48 com alvo 6:00-6:15)
        reached = [
            b["ok"] or (g is not None and g <= 0) for b, g in zip(blocks, gaps, strict=True)
        ]

        on = sum(reached)

        slow = [g for g, hit in zip(gaps, reached, strict=True) if not hit and g is not None]

        fast = [g for g in gaps if g is not None and g < 0]

        if on / len(blocks) >= _DELIVERED_SHARE:

            detail = f"{on} de {len(blocks)} blocos no ritmo-alvo ou mais rápido{told}"

            if fast:

                margin = abs(round(sum(fast) / len(fast)))

                detail += f" (em média {margin} s/km mais rápido que a faixa)"

            return Delivery(day, name, DELIVERED, detail, 0, rpe)

        mean_slow = round(sum(slow) / len(slow)) if slow else None

        slower = f", em média {mean_slow} s/km mais lento" if mean_slow else ""

        return Delivery(
            day, name, SOFT, f"{on} de {len(blocks)} blocos no ritmo-alvo{slower}{told}",
            mean_slow, rpe,
        )

    # na esteira o relógio não mede o ritmo (calibração) e o esforço do relógio não diz o que foi
    # corrido: Leonardo 09/10 (relógio descalibrado) e 23/10 (tiros a 5:27/km pelo painel, mais
    # rápidos que o alvo) apareciam como "sem intensidade" — não dá pra julgar
    if indoor or _indoor(act):

        detail = "esteira: o relógio não mede o ritmo (peça a velocidade do painel)"

        return Delivery(day, name, UNKNOWN, detail, None, rpe)

    if rpe is not None and rpe <= _SOFT_RPE:

        return Delivery(
            day, name, SOFT, f"blocos sem voltas medidas; ele sentiu {rpe}/10 (esforço de leve)",
            None, rpe,
        )

    if rpe is not None and rpe >= _HARD_RPE:

        detail = f"blocos sem voltas medidas; ele sentiu {rpe}/10"

        return Delivery(day, name, DELIVERED, detail, None, rpe)

    detail = "blocos sem voltas medidas e sem esforço relatado"

    return Delivery(day, name, UNKNOWN, detail, None, rpe)


def assess(
    plans, activities, log: dict[int, dict], rpes, today: date, weeks: int = WINDOW_WEEKS,
) -> DeliverySummary | None:
    """Os fortes prescritos nas últimas `weeks` semanas × os entregues. None sem nenhum forte
    prescrito na janela."""

    from app.application.history.training_patterns import TrainingPatterns

    by_day = {str(getattr(r, "day", "")): r for r in rpes or []}

    # dias em que ele correu na esteira: o relógio descalibra e o treino principal pode ter sido
    # gravado como corrida comum (Leonardo 09/10: 6,9 km "comum" + 1,2 km "Corrida em esteira")
    from app.application.history.weekly_buckets import activity_date

    treadmill_days = {
        activity_date(a) for a in activities
        if _treadmill_named(getattr(a, "name", None))
        or (getattr(a, "raw", None) or {}).get("trainer")
    }

    prescribed, items = 0, []

    for day, session, family, act in TrainingPatterns._sessions(plans, activities, today, weeks):

        if family not in QUALITY:

            continue

        if act is None:

            if day < today:

                prescribed += 1

            continue

        prescribed += 1

        entry = ExecutionLog._entry_for(act, log)

        rpe_row = by_day.get(day.isoformat())

        indoor = (
            activity_date(act) in treadmill_days
            or _treadmill_named(getattr(rpe_row, "note", None))
        )

        items.append(
            judge(session, act, entry, getattr(rpe_row, "rpe", None), day, indoor)
        )

    if not prescribed:

        return None

    delivered = [i for i in items if i.verdict == DELIVERED]

    soft = [i for i in items if i.verdict == SOFT]

    last = max((i.day for i in delivered), default=None)

    gaps = [i.gap_s for i in soft if i.gap_s]

    rpe_values = [i.rpe for i in items if i.rpe is not None]

    return DeliverySummary(
        prescribed=prescribed,
        done=len(items),
        delivered=len(delivered),
        soft=len(soft),
        unknown=len(items) - len(delivered) - len(soft),
        last_delivered=last,
        weeks_without=(today - last).days // 7 if last else None,
        mean_gap_s=round(sum(gaps) / len(gaps)) if gaps else None,
        mean_rpe=sum(rpe_values) / len(rpe_values) if rpe_values else None,
        items=sorted(items, key=lambda i: i.day),
    )


def for_profile(profile: str, today: date | None = None) -> DeliverySummary | None:
    """A partir do storage. Best-effort: qualquer falha = None."""

    try:

        from app.core.clock import today_local
        from app.domain.value_objects.sports import is_foot_sport
        from app.infrastructure.persistence.activity_archive_repository import (
            ActivityArchiveRepository,
        )
        from app.infrastructure.persistence.execution_log_store import ExecutionLogStore
        from app.infrastructure.persistence.session_rpe_repository import SessionRpeRepository
        from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

        repo = WeeklyPlanRepository()

        plans = list(repo.history(profile))

        current = repo.load(profile)

        if current is not None:

            plans.append(current)

        activities = [
            a for a in ActivityArchiveRepository().load_activities(profile)
            if is_foot_sport(a.sport)
        ]

        return assess(
            plans, activities, ExecutionLogStore().all(profile),
            SessionRpeRepository().load_sessions(profile), today or today_local(),
        )

    except Exception as e:  # noqa: BLE001

        print(f"Forte entregue falhou p/ '{profile}': {e}")

        return None


# --- o que o coach lê ------------------------------------------------------------------------


def _plural(n: int, one: str, many: str) -> str:

    return f"{n} {one if n == 1 else many}"


def headline(summary: DeliverySummary) -> str:
    """A frase-resumo, com os números (a mesma do dossiê e do aviso da auditoria)."""

    text = (
        f"prescritos {summary.prescribed}, feitos {summary.done}, entregues {summary.delivered}"
    )

    if summary.soft:

        text += f", sem intensidade {summary.soft}"

    if summary.unknown:

        text += f", sem medida {summary.unknown}"

    return text


def _tail(summary: DeliverySummary) -> str:

    bits = []

    if summary.mean_gap_s:

        bits.append(
            f"nos blocos medidos ficou em média {summary.mean_gap_s} s/km mais lento que o alvo"
        )

    if summary.mean_rpe is not None:

        bits.append(f"esforço percebido médio {summary.mean_rpe:.1f}/10")

    return "; ".join(bits)


def _line(item: Delivery) -> str:

    when = f"{_WEEKDAYS[item.day.weekday()]} {item.day:%d/%m}"

    return f"- {when} {item.workout_type}: {item.verdict} ({item.detail})"


_DIRECTIVE = (
    "CONHECIMENTO, não regra: mais um forte igual NÃO evolui quem não o entrega — e correr no dia "
    "certo não é entregar. Antes de repetir, ache a CAUSA com os números: (a) o alvo está acima do "
    "que ele sustenta hoje (recalibre pelo que ele fez nos blocos medidos); (b) ele não empurra "
    "— o "
    "esforço dele é de leve (≤3/10, FC abaixo da zona): dê a régua que ele entende (FC-alvo da "
    "zona, "
    "\"esforço 7 de 10\", repetições curtas com pace-guia, um teste curto de 3 km) e diga a ele o "
    "que você viu, sem repetir a mesma bronca; (c) esteira, calor ou terreno. A decisão é sua."
)


def render(summary: DeliverySummary | None, *, directive: bool = False) -> str:
    """O bloco do dossiê. Vazio sem forte prescrito. `directive` (voz do plano) acrescenta como
    tratar a causa; as outras vozes recebem os fatos."""

    if summary is None:

        return ""

    head = (
        f"FORTES: PRESCRITO × ENTREGUE (últimas {WINDOW_WEEKS} semanas — \"entregue\" = bateu o "
        "ritmo-alvo nos blocos medidos do relógio, ou ele sentiu 5/10 ou mais; fazer o treino no "
        "dia "
        f"certo não basta): {headline(summary)}."
    )

    if summary.last_delivered is None:

        head += " Nenhum forte entregue nestas semanas."

    else:

        head += (
            f" Último forte entregue: {summary.last_delivered:%d/%m} "
            f"(há {_plural(summary.weeks_without or 0, 'semana', 'semanas')})."
        )

    tail = _tail(summary)

    if tail:

        head += f" {tail[0].upper()}{tail[1:]}."

    lines = [head] + [_line(i) for i in summary.items[-6:]]

    if directive and summary.soft and not summary.delivered:

        lines.append(_DIRECTIVE)

    return "\n".join(lines)


def weeks_since(summary: DeliverySummary | None, today: date, window: int = WINDOW_WEEKS) -> int:
    """Há quantas semanas sem um forte entregue (a janela inteira quando nunca)."""

    if summary is None or summary.last_delivered is None:

        return window

    return max(0, (today - summary.last_delivered) // timedelta(days=7))
