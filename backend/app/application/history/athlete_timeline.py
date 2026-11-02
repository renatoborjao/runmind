"""A VISÃO DE TUDO — o histórico completo do atleta, semana a semana, com o que explica cada fase.

Renato (01/11): "o coach precisa ter visão de tudo; o histórico é super importante — é com isso que
nos municiamos pra ter um plano 100% aderente ao objetivo do atleta; uma semana ruim ou dias ruins não
deveriam matar o plano e a evolução". Até aqui o coach lia janelas (últimas 6-8 semanas, 200
mensagens, 26 leituras do corpo): do atleta antes disso ele só sabia pelo que a memória guardou, e
um mês raso depois de uma pausa médica virou "risco alto" (Renato 01/11) porque a pausa não aparecia
na mesma tela que a semana fraca.

Aqui sai a CURVA INTEIRA, sem buraco: uma linha por semana desde o primeiro treino (as 12 mais
recentes em detalhe, as anteriores resumidas por mês) com o que o coach prescreveu × o que ele fez,
o corpo na semana e o CONTEXTO que a explica (pausa, doença, lesão, viagem, prova, mudança de meta —
da memória em qualquer estado, vencida ou não, dos check-ins e das provas), mais as PROVAS (feitas e
à frente, com tempo e pace), os paces semana a semana e as melhores marcas por faixa de distância
(Renato: "que tenha o histórico de provas, tempos, paces — tudo"). Lê as fontes vivas E o
arquivo permanente, então nada que saiu de uma janela se perde. É calculado na hora, a partir do que
chega dia a dia: sempre fresco, sem job. DADO + conhecimento, nunca regra
([[feedback_ia_decide_sem_regras]], [[feedback_base_historico_sempre]]). Puro/determinístico."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median

from app.domain.value_objects.sports import is_run_sport

# as semanas mais recentes em linha própria; as anteriores entram resumidas por mês
RECENT_WEEKS = 12

# eventos listados (os mais recentes) — o resto da história fica nas linhas de semana/mês
MAX_EVENTS = 12

# pace (min/km) mais lento que isto = caminhada, não corrida (o mesmo corte do modelo de pace)
_MAX_RUN_PACE = 9.0

# o que mais explica uma semana vem primeiro: um período CURTO e específico (pausa, doença, lesão,
# prova) antes de um fato longo e geral (sono ruim há meses)
_NOTE_PRIORITY = {"prova": 0, "lesao": 1, "doenca": 1, "disponibilidade": 2, "vida": 3, "objetivo": 4,
                  "motivacao": 5, "checkin": 6}

# categorias da memória que EXPLICAM uma fase (preferência de tênis, por exemplo, não)
_EVENT_CATEGORIES = ("lesao", "disponibilidade", "vida", "objetivo", "motivacao")

_NOTE_CHARS = 46

_EVENT_CHARS = 120

_MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

# estados do corpo que são ALERTA (o resto é normal)
_ALERT_STATES = {"STRAINED": "sobrecarregado", "RECOVERY_FLAG": "recuperação em queda"}


@dataclass(slots=True)
class Event:

    day: date
    until: date | None
    kind: str
    text: str


@dataclass(slots=True)
class WeekRow:

    start: date
    km: float = 0.0
    seconds: float = 0.0                          # tempo correndo na semana (pace médio = seconds / km)
    runs: int = 0
    longest: float = 0.0
    prescribed: float | None = None
    deload: bool = False
    redone: int = 0                               # vezes que o plano da semana foi refeito/ajustado
    body: str | None = None                       # alerta do corpo na semana, se houve
    sleep: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Timeline:

    first: date
    weeks: list[WeekRow]
    events: list[Event]
    total_km: float
    total_runs: int
    best_week: tuple[date, float] | None
    longest_run: tuple[date, float] | None
    races: list[str]                              # provas feitas, cronológicas, com tempo e pace
    upcoming: list[str]                           # provas à frente
    bands: list[str]                              # melhor pace por faixa de distância


def _week_of(day: date) -> date:

    return day - timedelta(days=day.weekday())


def _day(value) -> date | None:

    try:

        return date.fromisoformat(str(value)[:10])

    except (TypeError, ValueError):

        return None


def _short(text: str, limit: int) -> str:

    text = " ".join((text or "").split())

    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build(
    activities,
    plans,
    plan_versions: list[dict],
    memory,
    checkins: list[dict],
    body_readings: list[dict],
    health,
    results: list[dict],
    today: date,
    records: dict | None = None,
    upcoming: list[dict] | None = None,
) -> Timeline | None:
    """A linha do tempo completa. `plans`: planos do coach; `plan_versions`: registros arquivados
    (versões substituídas, com `week_start`); `memory`: MemoryEntry em QUALQUER estado; `checkins` e
    `body_readings`: dicts (vivos + arquivados); `health`: leituras diárias do Garmin; `results`:
    provas cumpridas. None sem corrida."""

    # caminhada marcada como corrida (pace mais lento que 9:00/km) não é corrida
    runs = [
        a for a in activities
        if is_run_sport(a.sport) and (a.distance or 0) >= 1000 and a.moving_time
        and (a.moving_time / 60) / (a.distance / 1000) <= _MAX_RUN_PACE
    ]

    if not runs:

        return None

    from app.application.history.training_patterns import TrainingPatterns

    by_week: dict[date, WeekRow] = {}

    first = min(TrainingPatterns._local_day(a.start_date) for a in runs)

    current = _week_of(today)

    cursor = _week_of(first)

    while cursor <= current:

        by_week[cursor] = WeekRow(cursor)

        cursor += timedelta(weeks=1)

    longest_run: tuple[date, float] | None = None

    for act in runs:

        day = TrainingPatterns._local_day(act.start_date)

        km = (act.distance or 0) / 1000

        row = by_week[_week_of(day)]

        row.km += km

        row.seconds += act.moving_time or 0

        row.runs += 1

        row.longest = max(row.longest, km)

        if longest_run is None or km > longest_run[1]:

            longest_run = (day, km)

    for plan in plans:

        row = by_week.get(plan.week_start)

        if row is not None and plan.weekly_volume:

            row.prescribed = float(plan.weekly_volume)

            row.deload = bool(plan.is_deload)

    for record in plan_versions:

        week = _day((record.get("record") or {}).get("week_start"))

        if week in by_week:

            by_week[week].redone += 1

    # o corpo da semana: o pior estado de ALERTA lido nela (vivo + arquivo)
    for reading in body_readings:

        day = _day(reading.get("at") or reading.get("day"))

        state = reading.get("body_state")

        if day is None or state not in _ALERT_STATES or _week_of(day) not in by_week:

            continue

        by_week[_week_of(day)].body = _ALERT_STATES[state]

    sleeps: dict[date, list[float]] = defaultdict(list)

    for item in health or []:

        day = _day(getattr(item, "date", None))

        hours = getattr(item, "sleep_hours", None)

        if day is not None and hours:

            sleeps[_week_of(day)].append(hours)

    for week, values in sleeps.items():

        if week in by_week:

            by_week[week].sleep = round(mean(values), 1)

    events = _events(memory, checkins, results)

    # notas da semana: os eventos que a cobrem, o mais ESPECÍFICO primeiro (categoria que explica,
    # depois o período mais curto)
    for week, row in by_week.items():

        covering = [
            e for e in events
            if e.day <= week + timedelta(days=6) and (e.until or e.day) >= week
        ]

        covering.sort(key=lambda e: (
            _NOTE_PRIORITY.get(e.kind, 9), ((e.until or e.day) - e.day).days,
        ))

        row.notes = list(dict.fromkeys(_short(e.text, _NOTE_CHARS) for e in covering))

    weeks = sorted(by_week.values(), key=lambda r: r.start)

    best = max(weeks, key=lambda r: r.km)

    races = _races(runs, results, TrainingPatterns)

    ahead = _upcoming(upcoming or [], today)

    bands = _bands(records or {})

    return Timeline(
        first=first,
        weeks=weeks,
        events=events,
        total_km=sum(r.km for r in weeks),
        total_runs=sum(r.runs for r in weeks),
        best_week=(best.start, best.km) if best.km else None,
        longest_run=longest_run,
        races=races,
        upcoming=ahead,
        bands=bands,
    )


def _clock(seconds: float) -> str:

    total = round(seconds)

    if total >= 3600:

        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"

    return f"{total // 60}:{total % 60:02d}"


def _pace(seconds: float, km: float) -> str:

    per_km = round(seconds / km) if km else 0

    return f"{per_km // 60}:{per_km % 60:02d}"


def _races(runs, results: list[dict], patterns) -> list[str]:
    """TODAS as provas já corridas, cronológicas: as que o coach registrou (com a meta e se bateu)
    e as atividades que o Strava/nome marcam como prova e o coach não registrou."""

    from app.application.history.race_detector import RaceDetector

    found: list[tuple[date, str]] = []

    known_days: set[date] = set()

    for result in results:

        day = _day(result.get("date"))

        if day is None:

            continue

        known_days.add(day)

        goal = f", meta {result['target_time']}" if result.get("target_time") else ""

        verdict = " ✔ bateu" if result.get("beat") else (" ✘ não bateu" if "beat" in result else "")

        found.append((
            day,
            f"{day:%d/%m/%y} {result.get('race_label') or 'prova'}: {result.get('time') or '?'}"
            f" ({result.get('pace') or '?'}/km{goal}{verdict})",
        ))

    for act in runs:

        day = patterns._local_day(act.start_date)

        if day in known_days or not RaceDetector._is_race(act):

            continue

        km = (act.distance or 0) / 1000

        found.append((
            day,
            f"{day:%d/%m/%y} {_short(act.name or 'prova', 30)} ({km:.1f} km): "
            f"{_clock(act.moving_time or 0)} ({_pace(act.moving_time or 0, km)}/km)",
        ))

    return [text for _, text in sorted(found)]


def _upcoming(races: list[dict], today: date) -> list[str]:
    """As provas à frente (a data de hoje em diante), cronológicas."""

    out = []

    for race in sorted(races, key=lambda r: str(r.get("date"))):

        day = _day(race.get("date"))

        if day is None or day < today:

            continue

        goal = f", meta {race['target_time']}" if race.get("target_time") else ""

        priority = f", prioridade {race['priority']}" if race.get("priority") else ""

        out.append(f"{day:%d/%m/%y} {race.get('name') or 'prova'}{goal}{priority}")

    return out


def _bands(records: dict) -> list[str]:
    """O melhor pace médio por faixa de distância (do armazém de recordes), com o dia."""

    paces = records.get("pace_by_band") or {}

    dates = records.get("pace_by_band_dates") or {}

    out = []

    for band in sorted(paces, key=lambda b: float(str(b).split("-")[0])):

        value = paces[band]

        minutes = int(value)

        seconds = round((value - minutes) * 60)

        if seconds == 60:

            minutes, seconds = minutes + 1, 0

        day = _day(dates.get(band))

        out.append(f"{band} km: {minutes}:{seconds:02d}" + (f" ({day:%d/%m/%y})" if day else ""))

    return out


def _events(memory, checkins: list[dict], results: list[dict]) -> list[Event]:
    """O que explica uma fase: memória em qualquer estado (pausa, doença, lesão, viagem, objetivo),
    episódios de doença/dor dos check-ins e as provas. Cronológico."""

    out: list[Event] = []

    for entry in memory or []:

        if entry.category not in _EVENT_CATEGORIES:

            continue

        day = _day(entry.created_at)

        if day is None:

            continue

        until = _day(entry.expires_at) if entry.expires_at else None

        # só vale como PERÍODO quando é temporário e curto; fato durável marca o dia em que apareceu
        if until is not None and (until < day or (until - day).days > 120):

            until = None

        out.append(Event(day, until, entry.category, _short(entry.content, _EVENT_CHARS)))

    seen_illness: set[date] = set()

    for checkin in checkins:

        day = _day(checkin.get("day"))

        if day is None:

            continue

        if checkin.get("illness") and _week_of(day) not in seen_illness:

            seen_illness.add(_week_of(day))

            out.append(Event(day, None, "doenca", "relatou estar doente (check-in)"))

    for result in results:

        day = _day(result.get("date"))

        if day is not None:

            out.append(
                Event(
                    day, None, "prova",
                    f"PROVA {result.get('race_label') or ''} em {result.get('time') or '?'}"
                    + (" (bateu a meta)" if result.get("beat") else ""),
                )
            )

    # o mesmo fato gravado mais de uma vez (a extração repete) entra uma vez só
    unique: dict[tuple[str, str], Event] = {}

    for event in sorted(out, key=lambda e: e.day):

        unique.setdefault((event.kind, event.text[:50].lower()), event)

    return sorted(unique.values(), key=lambda e: e.day)


def _km(value: float) -> str:

    return f"{value:.0f}" if value >= 10 else f"{value:.1f}".replace(".", ",")


def _week_line(row: WeekRow) -> str:

    parts = [f"{row.start:%d/%m}: {_km(row.km)} km"]

    parts.append(f"{row.runs}x" + (f", maior {_km(row.longest)}" if row.runs else ""))

    if row.km and row.seconds:

        parts.append(f"pace {_pace(row.seconds, row.km)}")

    if row.prescribed is not None:

        plan = f"prescrito {_km(row.prescribed)}"

        if row.deload:

            plan += " (descarga)"

        if row.redone:

            plan += f", refeito {row.redone}x"

        parts.append(plan)

    if row.body:

        parts.append(f"corpo: {row.body}")

    if row.sleep:

        parts.append(f"sono {row.sleep:.1f}h".replace(".", ","))

    if row.notes:

        parts.append("[" + "; ".join(dict.fromkeys(row.notes[:2])) + "]")

    return "- " + " · ".join(parts)


def _month_line(label: str, rows: list[WeekRow]) -> str:

    ran = [r for r in rows if r.runs]

    kms = [r.km for r in rows]

    parts = [
        f"- {label}: {len(rows)} sem, média {_km(mean(kms))} km/sem "
        f"(de {_km(min(kms))} a {_km(max(kms))}), {sum(r.runs for r in rows)} corridas, "
        f"maior {_km(max((r.longest for r in rows), default=0.0))}"
    ]

    km_total = sum(r.km for r in rows)

    if km_total and sum(r.seconds for r in rows):

        parts[0] += f", pace médio {_pace(sum(r.seconds for r in rows), km_total)}"

    stopped = len(rows) - len(ran)

    if stopped:

        parts.append(f"{stopped} sem sem correr")

    notes = list(dict.fromkeys(n for r in rows for n in r.notes))

    if notes:

        parts.append("[" + "; ".join(notes[:3]) + "]")

    return " · ".join(parts)


def render(timeline: Timeline | None, *, plan_voice: bool = False) -> str:
    """O bloco pro prompt. Vazio sem histórico. `plan_voice` acrescenta o conhecimento de como ler."""

    if timeline is None:

        return ""

    weeks = timeline.weeks

    lines = [
        f"HISTÓRICO COMPLETO DELE (desde {timeline.first:%d/%m/%Y}: {len(weeks)} semanas, "
        f"{timeline.total_runs} corridas, {_km(timeline.total_km)} km) — a curva inteira e o que "
        "explica cada fase; cada linha é uma semana seg–dom:"
    ]

    recent = weeks[-RECENT_WEEKS:]

    older = weeks[: len(weeks) - len(recent)]

    by_month: dict[tuple[int, int], list[WeekRow]] = defaultdict(list)

    for row in older:

        by_month[(row.start.year, row.start.month)].append(row)

    for (year, month), rows in sorted(by_month.items()):

        lines.append(_month_line(f"{_MONTHS[month - 1]}/{year % 100:02d}", rows))

    lines.extend(_week_line(row) for row in recent)

    marks = []

    if timeline.best_week:

        marks.append(f"melhor semana {_km(timeline.best_week[1])} km ({timeline.best_week[0]:%d/%m})")

    if timeline.longest_run:

        marks.append(f"maior corrida {_km(timeline.longest_run[1])} km ({timeline.longest_run[0]:%d/%m})")

    if marks:

        lines.append("Marcos: " + " · ".join(marks) + ".")

    if timeline.bands:

        lines.append("Melhor pace médio por faixa de distância: " + " · ".join(timeline.bands) + ".")

    lines.append(
        "PROVAS FEITAS: " + ("; ".join(timeline.races) if timeline.races else "nenhuma registrada") + "."
    )

    if timeline.upcoming:

        lines.append("PROVAS À FRENTE: " + "; ".join(timeline.upcoming) + ".")

    shown = timeline.events[-MAX_EVENTS:]

    if shown:

        lines.append("O QUE EXPLICA AS FASES (do que ele contou e do que aconteceu; em qualquer estado):")

        for event in shown:

            span = f"{event.day:%d/%m}" + (f"–{event.until:%d/%m}" if event.until else "")

            lines.append(f"- {span} ({event.kind}): {event.text}")

    if plan_voice:

        lines.append(
            "CONHECIMENTO, não regra: este é o atleta INTEIRO, não só as últimas semanas. Uma semana "
            "fraca com motivo na mesma linha (pausa, gripe, chuva, viagem) é contexto, não queda de "
            "capacidade; o que ele SUSTENTOU antes de uma parada é o que ele volta a sustentar, num "
            "ritmo que o corpo permita. Planeje pela trajetória toda — onde ele esteve, por que "
            "oscilou, pra onde o objetivo o leva — e nunca por uma semana ou um sinal isolado."
        )

    return "\n".join(lines)


def for_profile(profile: str, activities, today: date, *, plan_voice: bool = False) -> str:
    """O bloco do atleta a partir do storage: fontes vivas + arquivo permanente. Best-effort — em
    qualquer falha devolve vazio e o resto do dossiê segue."""

    try:

        from dataclasses import asdict

        from app.infrastructure.persistence.body_reading_history_repository import (
            BodyReadingHistoryRepository,
        )
        from app.infrastructure.persistence.checkin_repository import CheckinRepository
        from app.infrastructure.persistence.garmin_health_repository import (
            GarminHealthRepository,
        )
        from app.infrastructure.persistence.permanent_archive import PermanentArchive
        from app.infrastructure.persistence.personal_record_repository import (
            PersonalRecordRepository,
        )
        from app.infrastructure.persistence.race_repository import RaceRepository
        from app.infrastructure.persistence.race_result_repository import RaceResultRepository
        from app.infrastructure.persistence.runner_memory_repository import (
            RunnerMemoryRepository,
        )
        from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

        plans_repo = WeeklyPlanRepository()

        plans = list(plans_repo.history(profile))

        current = plans_repo.load(profile)

        if current is not None and all(p.week_start != current.week_start for p in plans):

            plans.append(current)

        plans = [p for p in plans if getattr(p, "source", "runmind") == "runmind"]

        body_repo = BodyReadingHistoryRepository()

        checkin_repo = CheckinRepository()

        body = [asdict(s) for s in body_repo.load(profile)] + [
            e["record"] for e in PermanentArchive.load(body_repo.storage, "body_readings", profile)
        ]

        checkins = [asdict(c) for c in checkin_repo.load(profile)] + [
            e["record"] for e in PermanentArchive.load(checkin_repo.storage, "checkins", profile)
        ]

        timeline = build(
            activities,
            plans,
            PermanentArchive.load(plans_repo.storage, "plan_versions", profile),
            RunnerMemoryRepository().load(profile),
            checkins,
            body,
            GarminHealthRepository().load(profile),
            RaceResultRepository().load(profile),
            today,
            records=PersonalRecordRepository().load(profile),
            upcoming=RaceRepository().load(profile),
        )

        return render(timeline, plan_voice=plan_voice)

    except Exception as e:  # noqa: BLE001 — a visão longa nunca derruba o dossiê

        print(f"Visão de tudo falhou p/ '{profile}': {e}")

        return ""
