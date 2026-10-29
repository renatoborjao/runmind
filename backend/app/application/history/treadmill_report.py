"""ESTEIRA — o que o atleta CONTA vale mais que o relógio.

Na esteira o relógio não mede o ritmo (calibração, sem GPS): o Leonardo correu o ritmo de
prova de 09/10 com o relógio descalibrado e, em 23/10, fez os tiros de 400 m na velocidade 11
do painel — pace 5:27, MAIS RÁPIDO que o alvo de 5:40-5:55 — e o sistema leu os dois como
"forte sem intensidade". O atleta já conta tudo isso no chat ("tiros na velocidade 11, que é
pace 5:27; leve na 8, 7:30"); só não entrava em lugar nenhum.

Aqui o relato vira registro: o cérebro do chat (na MESMA chamada que já lê a percepção dele —
sem custo novo) devolve os trechos com pace ou velocidade, e isto converte, compara com a
faixa que o plano prescreveu e grava no registro de execução (o mesmo que o relógio alimenta
nos treinos de rua) marcado como relato. Puro na conversão; a gravação é best-effort."""

from datetime import date

from app.application.history.execution_log import ExecutionLog
from app.domain.entities.workout_step import INTERVAL, RUN

# um relato fora disto é engano de digitação ("pace 52" ou "velocidade 110"), não corrida
_MIN_PACE_S = 180
_MAX_PACE_S = 720

_MAX_ITEMS = 8
_MAX_REPS = 20
_MAX_METERS = 50_000


def _seconds(pace) -> int | None:
    """"5:27" -> 327. None se não for um pace."""

    if not pace or ":" not in str(pace):

        return None

    try:

        minutes, seconds = str(pace).strip().split(":")[:2]

        return int(minutes) * 60 + int(seconds)

    except (TypeError, ValueError):

        return None


def _pace(seconds: int) -> str:

    return f"{seconds // 60}:{seconds % 60:02d}"


def _number(value) -> float | None:

    try:

        number = float(str(value).replace(",", "."))

    except (TypeError, ValueError):

        return None

    return number if number > 0 else None


def normalize(raw) -> list[dict]:
    """Os trechos que ele contou: [{kind: interval|run, pace: "m:ss", meters, reps}]. Aceita pace
    ("5:27") OU velocidade do painel em km/h (11 → 5:27). O que não fecha é descartado."""

    if not isinstance(raw, list):

        return []

    items = []

    for entry in raw[:_MAX_ITEMS]:

        if not isinstance(entry, dict):

            continue

        kind_text = str(entry.get("kind") or "").lower()

        kind = "interval" if kind_text.startswith("int") or "tiro" in kind_text else "run"

        seconds = _seconds(entry.get("pace"))

        if seconds is None:

            speed = _number(entry.get("speed_kmh"))

            seconds = round(3600 / speed) if speed else None

        if seconds is None or not _MIN_PACE_S <= seconds <= _MAX_PACE_S:

            continue

        meters = _number(entry.get("meters"))

        reps = _number(entry.get("reps"))

        items.append({
            "kind": kind,
            "pace": _pace(seconds),
            "meters": int(meters) if meters and meters <= _MAX_METERS else None,
            "reps": int(reps) if reps and 1 <= reps <= _MAX_REPS else None,
        })

    return items


def _band(session, step_kind: str) -> str | None:
    """A faixa que o plano prescreveu pra esse tipo de trecho (None se há mais de uma)."""

    if session is None:

        return None

    bands = ExecutionLog._targets(session.steps, kinds={step_kind})

    return next(iter(bands)) if len(bands) == 1 else None


def _planned_reps(steps, multiplier: int = 1) -> int:
    """Quantos tiros o plano prescreveu (respeitando os grupos que repetem)."""

    total = 0

    for step in steps or []:

        if getattr(step, "kind", None) == INTERVAL:

            total += multiplier

        inner = multiplier * (step.reps or 1) if getattr(step, "is_repeat", False) else multiplier

        total += _planned_reps(getattr(step, "steps", None), inner)

    return total


def blocks_from_report(items: list[dict], session=None) -> list[dict]:
    """Os blocos no formato do registro de execução. Só entra o que dá pra COMPARAR: tiros (sempre)
    e trechos contínuos com faixa prescrita — o leve solto não é estímulo e só faria ruído."""

    from app.application.history.stimulus_delivery import _gap_seconds

    blocks = []

    for item in items:

        step_kind = INTERVAL if item["kind"] == "interval" else RUN

        target = _band(session, step_kind)

        if step_kind == RUN and target is None:

            continue

        gap = _gap_seconds(item["pace"], target) if target else None

        # ele nem sempre diz quantos foram: sem número, vale o que o plano prescreveu
        planned = _planned_reps(session.steps) if session and step_kind == INTERVAL else 0

        for _ in range(item.get("reps") or planned or 1):

            blocks.append({
                "kind": step_kind,
                "m": item.get("meters") or 0,
                "pace": item["pace"],
                "hr": None,
                "target": target,
                "ok": None if gap is None else gap == 0,
            })

    return blocks


def record(profile: str, day: date, raw) -> bool:
    """Grava o relato dele no registro de execução da corrida daquele dia (a mais longa). True se
    gravou. Best-effort: sem corrida no dia, sem trecho comparável ou qualquer falha = False."""

    items = normalize(raw)

    if not items:

        return False

    try:

        from app.application.coach.intelligence.perception_recorder import PerceptionRecorder
        from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
        from app.infrastructure.persistence.execution_log_store import ExecutionLogStore
        from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

        activity = PerceptionRecorder._run_on(profile, day)

        if activity is None:

            return False

        repository = WeeklyPlanRepository()

        plans = list(repository.history(profile))

        current = repository.load(profile)

        if current is not None:

            plans.append(current)

        session = None

        for plan in plans:

            for planned, matched in WeeklyPlanMatcher.pairs(plan, [activity]):

                if matched is not None:

                    session = planned

        blocks = blocks_from_report(items, session)

        if not blocks:

            return False

        ExecutionLogStore().record(
            profile, int(activity.id), day.isoformat(), (activity.distance or 0) / 1000,
            {"blocks": blocks, "missing": [], "reported": True},
        )

        return True

    except Exception as e:  # noqa: BLE001

        print(f"Relato da esteira falhou p/ '{profile}': {e}")

        return False


# --- a pergunta do pós-treino ----------------------------------------------------------------

ASK_LINE = (
    "🧮 Esse treino foi na esteira, e o relógio não mede o ritmo direito lá. Me conta a velocidade "
    "do painel (km/h) ou o pace dos tiros e do leve que eu registro certinho."
)


def is_treadmill(activity) -> bool:
    """Corrida na esteira: a marca do relógio ou o nome da gravação."""

    from app.application.history.stimulus_delivery import _indoor

    return _indoor(activity)
