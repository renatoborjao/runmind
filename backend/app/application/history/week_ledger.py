"""SEMANAS ANTERIORES — o que o coach PRESCREVEU × o que o atleta FEZ, semana a semana, numa leitura
só: o ponto de partida de TODA semana nova.

O plano de domingo recebia o prescrito num lugar (a trajetória: "volume planejado
12·12·9·13·8·22") e o feito em outro (a evolução semana a semana), e nada os punha lado a lado nem
mostrava o que o próprio coach quis em cada semana. Resultado (Leonardo, 21/10): depois de uma
semana de 8 km o plano seguinte pediu 22 km — +175% sobre o que ele fez, num atleta que sustenta
~12 km — porque cada semana nascia do papel da anterior, não do que o corpo dele cumpriu. O que o
atleta fez é o chão da próxima semana: sessão não cumprida não é dose absorvida, e carga a mais
que o papel já foi paga.

Aqui sai a ponte: por semana, o objetivo que o coach deu, o volume e as sessões que prescreveu, o
que ele correu (km, corridas, maior corrida), o que cumpriu/não fez/ainda falta, o salto do papel
sobre o feito da semana anterior e a faixa da rota daquela semana (quando o plano guardou). É DADO
+ CONHECIMENTO pro coach ([[feedback_ia_decide_sem_regras]]); a decisão é dele.
Puro/determinístico."""

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from app.application.history.stimulus_ledger import (
    FARTLEK,
    HILLS,
    PROGRESSION,
    RACE_PACE,
    THRESHOLD,
    VO2,
    StimulusLedger,
)
from app.application.history.weekly_buckets import activity_date
from app.domain.entities.activity import Activity
from app.domain.entities.training_plan import TrainingPlan
from app.domain.value_objects.sports import is_run_sport

WINDOW_WEEKS = 6

_MIN_RUN_M = 1000

# sessões que carregam o estímulo forte da semana (o leve e o longão ficam de fora)
_QUALITY = {RACE_PACE, HILLS, FARTLEK, THRESHOLD, VO2, PROGRESSION}

# o papel só vira nota quando mudou isto sobre o que ele FEZ na semana anterior
_JUMP = 0.25

_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")

_OBJECTIVE_CHARS = 95

_RUN_KINDS = ("run", "walk", "run_walk")


@dataclass(slots=True)
class LedgerWeek:

    week_start: date
    phase: str
    objective: str
    deload: bool
    planned_km: float
    planned_sessions: int
    planned_long_km: float
    planned_key: list[str]
    done_km: float
    done_runs: int
    done_long_km: float
    fulfilled: int
    missed: list[str]
    pending: list[str]
    extras: int
    in_progress: bool
    prev_done_km: float
    quality_done_km: float
    route_km: tuple[float, float] | None = None
    route_note: str | None = None


def _week_of(day: date) -> date:

    return day - timedelta(days=day.weekday())


def run_km_by_week(activities: list[Activity]) -> dict[date, list[float]]:
    """Os km de cada corrida, por semana (segunda). Só corrida de verdade (≥ 1 km)."""

    out: dict[date, list[float]] = {}

    for act in activities:

        if not is_run_sport(act.sport) or (act.distance or 0) < _MIN_RUN_M:

            continue

        out.setdefault(_week_of(activity_date(act)), []).append(act.distance / 1000)

    return out


def _planned_km(plan: TrainingPlan) -> float:

    summed = sum(
        s.effective_distance_km or 0.0 for s in plan.sessions if s.kind in _RUN_KINDS
    )

    return float(plan.weekly_volume or summed or 0.0)


def _short(text: str | None) -> str:

    clean = " ".join((text or "").split())

    if len(clean) <= _OBJECTIVE_CHARS:

        return clean

    cut = clean[:_OBJECTIVE_CHARS].rsplit(" ", 1)[0].rstrip(",;:-")

    return cut + "…"


def build(
    plans: list[TrainingPlan],
    activities: list[Activity],
    today: date,
    ref_week: date,
    weeks: int = WINDOW_WEEKS,
) -> list[LedgerWeek]:
    """As últimas `weeks` semanas ANTES de `ref_week` (a que está sendo montada, ou a de hoje),
    da mais antiga pra mais recente, só as que tiveram plano nosso. A semana em andamento (a
    anterior à nova, num meio de semana) mostra o que ainda falta em vez de contar furo."""

    from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher

    runs = [
        a for a in activities if is_run_sport(a.sport) and (a.distance or 0) >= _MIN_RUN_M
    ]

    km_by_week = run_km_by_week(activities)

    by_week = {p.week_start: p for p in plans if p.sessions and p.source == "runmind"}

    out: list[LedgerWeek] = []

    for back in range(weeks, 0, -1):

        start = ref_week - timedelta(weeks=back)

        plan = by_week.get(start)

        if plan is None:

            continue

        done = km_by_week.get(start, [])

        closed = today >= start + timedelta(days=6)

        fulfilled, missed, pending, key, quality_done = 0, [], [], [], 0.0

        planned_runs = []

        for session, act in WeeklyPlanMatcher.pairs(plan, runs):

            if getattr(session, "kind", "run") not in _RUN_KINDS:

                continue

            planned_runs.append(session)

            family = StimulusLedger.classify(session.workout_type)

            if family in _QUALITY and session.workout_type not in key:

                key.append(session.workout_type)

            if act is not None:

                fulfilled += 1

                if family in _QUALITY:

                    quality_done = max(quality_done, (act.distance or 0) / 1000)

                continue

            when = plan.session_date(session)

            label = f"{_WEEKDAYS[when.weekday()]} {session.workout_type}"

            km = session.effective_distance_km

            if km:

                label += f" {km:g} km"

            (missed if closed or when < today else pending).append(label)

        with_km = [s.effective_distance_km for s in planned_runs if s.effective_distance_km]

        planned_long = max(with_km) if with_km and len(planned_runs) >= 2 else 0.0

        route = (plan.route or {}).get("weeks") or []

        band = route[0].get("km") if route else None

        out.append(
            LedgerWeek(
                week_start=start,
                phase=plan.phase or "",
                objective=_short(plan.weekly_objective),
                deload=bool(plan.is_deload),
                planned_km=_planned_km(plan),
                planned_sessions=len(planned_runs),
                planned_long_km=planned_long,
                planned_key=key,
                done_km=sum(done),
                done_runs=len(done),
                done_long_km=max(done) if done else 0.0,
                fulfilled=fulfilled,
                missed=missed,
                pending=pending,
                extras=max(0, len(done) - fulfilled),
                in_progress=not closed,
                prev_done_km=sum(km_by_week.get(start - timedelta(weeks=1), [])),
                quality_done_km=quality_done,
                route_km=(float(band[0]), float(band[1])) if band else None,
                route_note=plan.route_note or None,
            )
        )

    return out


def typical(ledger: list[LedgerWeek]) -> tuple[float, float, float] | None:
    """(mediana dos km das semanas FECHADAS em que ele correu, melhor semana, maior corrida) —
    o que ele sustenta de verdade. None sem nenhuma semana fechada com corrida."""

    ran = [w for w in ledger if not w.in_progress and w.done_km > 0]

    if not ran:

        return None

    return (
        median(w.done_km for w in ran),
        max(w.done_km for w in ran),
        max(w.done_long_km for w in ran),
    )


def _num(value: float) -> str:

    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}".replace(".", ",")


def _plural(count: int, one: str, many: str) -> str:

    return f"{count} {one if count == 1 else many}"


def _line(week: LedgerWeek) -> str:

    head = f"- {week.week_start:%d/%m}"

    if week.in_progress:

        head += " (em andamento)"

    tags = [t for t in (week.phase, "descarga" if week.deload else "") if t]

    if tags:

        head += f" [{' · '.join(tags)}]"

    if week.objective:

        head += f" \"{week.objective}\""

    sessions = _plural(week.planned_sessions, "sessão", "sessões")

    planned = f"prescreveu ~{_num(week.planned_km)} km em {sessions}"

    detail = []

    if week.planned_long_km:

        detail.append(f"maior {_num(week.planned_long_km)} km")

    if week.planned_key:

        detail.append("fortes: " + ", ".join(week.planned_key))

    if detail:

        planned += f" ({'; '.join(detail)})"

    if week.done_runs:

        done = f"fez {_num(week.done_km)} km em {_plural(week.done_runs, 'corrida', 'corridas')}"

        if week.in_progress:

            done += " até agora"

        elif week.planned_km:

            done += f" ({(week.done_km / week.planned_km - 1) * 100:+.0f}%)"

        done += f", maior {_num(week.done_long_km)} km"

    else:

        done = "não correu" if not week.in_progress else "ainda não correu"

    parts = [f"{planned} → {done}"]

    if week.planned_sessions:

        cumpriu = f"cumpriu {week.fulfilled} de {week.planned_sessions} do plano"

        if week.extras:

            cumpriu += f" + {week.extras} a mais"

        parts.append(cumpriu)

    if week.missed:

        parts.append("NÃO fez: " + ", ".join(week.missed))

    if week.pending:

        parts.append("falta: " + ", ".join(week.pending))

    text = "; ".join(parts) + "."

    if (
        week.prev_done_km > 0
        and week.planned_km
        and abs(week.planned_km / week.prev_done_km - 1) >= _JUMP
    ):

        text += (
            f" O papel foi {(week.planned_km / week.prev_done_km - 1) * 100:+.0f}% sobre o que "
            f"ele fez na semana anterior ({_num(week.prev_done_km)} km)."
        )

    if week.route_km:

        text += f" Rota previa {_num(week.route_km[0])}–{_num(week.route_km[1])} km."

    if week.route_note:

        text += f" Seu motivo: {week.route_note}"

    return f"{head}: {text}"


_HEADER = (
    "SEMANAS ANTERIORES — o que VOCÊ prescreveu × o que ELE fez, semana a semana (da mais antiga "
    "p/ a mais recente; só as semanas com plano nosso). É o PONTO DE PARTIDA da semana nova: o "
    "plano não nasce do papel, nasce do que o corpo e a rotina dele cumpriram."
)

_DIRECTIVE = (
    "CONHECIMENTO, não regra: a semana nova CONTINUA estas. Parta do que ele FEZ — o que ele não "
    "cumpriu não foi dose absorvida (refaça ou ajuste o degrau em vez de somar por cima como se "
    "tivesse feito); o que ele fez além do papel é carga que o corpo já pagou (parta dali); um "
    "papel bem acima do que ele sustenta tem custo, e bem abaixo desperdiça o que ele mostrou "
    "aguentar — se a semana nova se afasta do que ele vem fazendo, diga por quê. No propósito de "
    "cada sessão diga o que ela herda da semana anterior (o que ele fez) e o que avança."
)


def render(ledger: list[LedgerWeek], *, directive: bool = False) -> str:
    """O bloco do dossiê. Vazio sem semana com plano. `directive` (só a voz do plano) acrescenta
    o conhecimento de como usar; as outras vozes recebem os fatos."""

    if not ledger:

        return ""

    lines = [_HEADER] + [_line(week) for week in ledger]

    usual = typical(ledger)

    if usual is not None:

        median_km, best_km, longest = usual

        lines.append(
            f"O que ele SUSTENTA (semanas fechadas em que correu): mediana ~{_num(median_km)} "
            f"km/semana, melhor semana {_num(best_km)} km, maior corrida {_num(longest)} km."
        )

    if directive:

        lines.append(_DIRECTIVE)

    return "\n".join(lines)
