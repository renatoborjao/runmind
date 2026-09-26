"""Contexto dos cards de COMPARTILHAR do app que usam o que só o Ritmind tem:

- sessão do PLANO que uma corrida cumpriu (card "Plano × feito") — mesmo
  casamento do plano (WeeklyPlanMatcher: dia primeiro, depois distância), sobre
  o plano daquela semana (vigente ou histórico);
- META de km de um período (card "Meta") — soma das sessões planejadas nas
  datas do período;
- FRASE curta do coach sobre o treino (card "Coach diz") — gerada UMA vez a
  partir da análise já feita, só quando alguém abre o compartilhar, e guardada
  junto da análise (não pesa no pós-treino).

Ver [[project_app_atleta]]."""

import asyncio
import re
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from google.genai import types

from app.application.history.planned_execution_matcher import (
    PlannedExecutionMatcher,
)
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.config import get_settings
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import INTERVAL, RUN, WorkoutStep
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
)
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.gemini.client import generate_text
from app.infrastructure.persistence.share_phases_store import SharePhasesStore
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)
from app.infrastructure.persistence.workout_analysis_repository import (
    WorkoutAnalysisRepository,
)

QUOTE_MAX_CHARS = 140

QUOTE_PROMPT = """Você é o coach de corrida do Ritmind. Abaixo está a análise \
que você fez de um treino do atleta.

ANÁLISE:
{analysis}

Escreva UMA frase curta sobre esse treino pra ir num card que o atleta vai \
postar no story do Instagram. Regras:
- pt-BR, tom de treinador orgulhoso e direto, máximo {max_chars} caracteres;
- destaque o ponto mais positivo e concreto (ritmo, constância, progressão,
  distância) usando algum número real da análise quando fizer sentido;
- sem emojis, sem hashtags, sem aspas, sem o nome do atleta, sem conselhos.

Responda APENAS com a frase."""


def _plans(profile: str) -> list[TrainingPlan]:

    repo = WeeklyPlanRepository()

    plans = repo.history(profile)

    current = repo.load(profile)

    # o vigente vale sobre o snapshot da mesma semana
    if current is not None:

        plans = [p for p in plans if p.week_start != current.week_start]

        plans.append(current)

    return plans


def _plan_for(profile: str, day: date) -> TrainingPlan | None:

    for plan in _plans(profile):

        if plan.week_start <= day <= plan.week_start + timedelta(days=6):

            return plan

    return None


def _as_activity(idx: int, item: dict) -> SimpleNamespace:
    """Corrida do feed no formato que o WeeklyPlanMatcher lê (id, data,
    distância em metros)."""

    raw = item.get("datetime") or item["date_iso"]

    try:

        start = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))

    except ValueError:

        start = datetime.fromisoformat(item["date_iso"])

    # o dia que vale é o LOCAL (date_iso) — horário só desempata
    local_day = date.fromisoformat(item["date_iso"][:10])

    start = datetime.combine(local_day, start.time())

    return SimpleNamespace(
        id=idx, start_date=start, distance=(item.get("distance_km") or 0) * 1000,
    )


def planned_session(
    profile: str, feed: list[dict], date_iso: str, km: float,
) -> dict | None:
    """Sessão do plano que a corrida (data + km) cumpriu, no formato do card,
    ou None (treino extra, sem plano naquela semana, sem casamento)."""

    session = match_session(profile, feed, date_iso, km)

    return None if session is None else session_card(session)


def session_card(session) -> dict:

    return {
        "workout_type": session.workout_type,
        "distance_km": session.planned_distance_km,
        "duration_min": session.planned_duration_minutes,
        **_planned_pace(session),
    }


def match_session(profile: str, feed: list[dict], date_iso: str, km: float):
    """A PlannedSession que a corrida cumpriu (WeeklyPlanMatcher: dia
    primeiro, depois distância) ou None."""

    day = date.fromisoformat(date_iso[:10])

    plan = _plan_for(profile, day)

    if plan is None or not plan.sessions:

        return None

    week_end = plan.week_start + timedelta(days=6)

    week_items = [
        it for it in feed
        if plan.week_start <= date.fromisoformat(it["date_iso"][:10]) <= week_end
        and (it.get("distance_km") or 0) > 0
    ]

    activities = [_as_activity(i, it) for i, it in enumerate(week_items)]

    current = next(
        (
            a for a, it in zip(activities, week_items)
            if it["date_iso"][:10] == date_iso[:10]
            and abs((it.get("distance_km") or 0) - km) < 0.6
        ),
        None,
    )

    if current is None:

        return None

    session = WeeklyPlanMatcher.match(plan, activities, current)

    if session is None or not (session.workout_type or "").strip():

        return None

    return session


def _main_blocks(steps: list[WorkoutStep]) -> list[tuple[str, str | None, str | None]]:
    """Blocos PRINCIPAIS com ritmo, em ordem (achata repetições; aquecimento,
    recuperação e desaquecimento ficam de fora): (tipo, pace_min, pace_max)."""

    out: list[tuple[str, str | None, str | None]] = []

    for step in steps:

        if step.is_repeat:

            out.extend(_main_blocks(step.steps))

        elif step.kind in (RUN, INTERVAL) and (step.pace_min or step.pace_max):

            out.append((step.kind, step.pace_min, step.pace_max))

    return out


def _range(pmin: str | None, pmax: str | None) -> str:

    if pmin and pmax and pmin != pmax:

        return f"{pmin}–{pmax}"

    return pmin or pmax or ""


def _planned_pace(session) -> dict:
    """Ritmo do plano pro card. O ritmo quase sempre mora nos PASSOS do treino
    (os campos target_pace_* ficam vazios no treino estruturado) — sem isso o
    card dizia "ritmo livre" num treino com ritmo prescrito.

    - contínuo (todos os blocos principais no mesmo ritmo): pace_min/pace_max
      preenchidos → o card compara com a média do atleta;
    - estruturado (progressivo / tiros): só `pace_label` descritivo
      ("6:20–6:45 → 5:25–5:40", "4:50–5:05 (tiros)") e SEM comparação — a
      média de um fartlek mistura tiro e trote e daria veredito falso;
    - nada em lugar nenhum: tudo None (o card mostra "livre")."""

    if session.target_pace_min or session.target_pace_max:

        return {
            "pace_min": session.target_pace_min,
            "pace_max": session.target_pace_max,
            "pace_label": _range(session.target_pace_min, session.target_pace_max),
            "pace_structured": False,
        }

    blocks = _main_blocks(session.steps or [])

    if not blocks:

        return {"pace_min": None, "pace_max": None, "pace_label": None, "pace_structured": False}

    ranges: list[str] = []

    for _, pmin, pmax in blocks:

        r = _range(pmin, pmax)

        if not ranges or ranges[-1] != r:

            ranges.append(r)

    if len(ranges) == 1 and all(kind == RUN for kind, _, _ in blocks):

        _, pmin, pmax = blocks[0]

        return {"pace_min": pmin, "pace_max": pmax, "pace_label": ranges[0], "pace_structured": False}

    if all(kind == INTERVAL for kind, _, _ in blocks):

        label = f"{ranges[0]} (tiros)" if len(ranges) == 1 else " / ".join(ranges)

    else:

        label = " → ".join(ranges)

    return {"pace_min": None, "pace_max": None, "pace_label": label, "pace_structured": True}


# ritmo de referência (min/km) pra estimar km de sessão por TEMPO sem
# estimativa guardada — só pesa a distribuição da semana, o total vem do
# weekly_volume do plano
_EST_MIN_PER_KM = 6.0


def _session_km(session) -> float:

    km = session.effective_distance_km

    if km:

        return km

    if session.planned_duration_minutes:

        return session.planned_duration_minutes / _EST_MIN_PER_KM

    return 0.0


def period_goal_km(profile: str, start: date, end: date) -> float | None:
    """Meta de km do período pelo PLANO. O total de cada semana é o
    `weekly_volume` do plano (o que o coach prescreveu), distribuído pelas
    sessões na proporção do km de cada uma (sessão por tempo entra pelo km
    estimado) — assim o mês pega só os dias dele e treino "45 min" não some
    da meta. None quando não há plano no período."""

    total = 0.0

    found = False

    for plan in _plans(profile):

        weights = [(session, _session_km(session)) for session in plan.sessions]

        week_w = sum(w for _, w in weights)

        if week_w <= 0:

            continue

        target = plan.weekly_volume if (plan.weekly_volume or 0) > 0 else week_w

        for session, w in weights:

            try:

                d = plan.session_date(session)

            except Exception:

                continue

            if start <= d <= end and w > 0:

                total += w * target / week_w

                found = True

    return round(total, 1) if found else None


# ---- EXECUTADO fase a fase (voltas do relógio × passos do plano) -----------


def _pace_sec(value: str | None) -> int | None:

    m = re.match(r"^(\d+):(\d{2})", (value or "").strip())

    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _amount(distance_m: float | None, duration_sec: int | None) -> str:
    """"200m" / "1 km" / "2min" / "90s" — o tamanho de UM passo."""

    if distance_m:

        return f"{distance_m / 1000:g} km" if distance_m >= 1000 else f"{int(round(distance_m))}m"

    if duration_sec:

        return f"{duration_sec // 60}min" if duration_sec % 60 == 0 else f"{duration_sec}s"

    return ""


def _total_amount(blocks) -> str:
    """Tamanho somado de um trecho contínuo ("10 km", "30min")."""

    dist = sum(b.planned_distance_m or 0 for b in blocks)

    if dist:

        return f"{round(dist / 1000, 1):g} km"

    dur = sum(b.planned_duration_sec or 0 for b in blocks)

    if dur:

        return f"{round(dur / 60):g}min"

    return f"{round(sum(b.executed_distance_m for b in blocks) / 1000, 1):g} km"


def build_phases(blocks) -> list[dict] | None:
    """Agrupa os blocos PRINCIPAIS executados (corrida contínua / tiro com
    alvo de ritmo; aquecimento, recuperação e desaquecimento ficam de fora) em
    FASES: blocos seguidos com o mesmo alvo viram uma fase. Série de tiros
    (≥2) = "tiros" (o card mostra tiro a tiro); o resto = "bloco" (uma linha
    por trecho: 10 km leve, 4 km forte…)."""

    main = [
        b for b in blocks
        if b.kind in (RUN, INTERVAL) and (b.pace_min or b.pace_max)
    ]

    if not main:

        return None

    groups: list[list] = []

    for b in main:

        if groups and (groups[-1][0].kind, groups[-1][0].pace_min, groups[-1][0].pace_max) == (b.kind, b.pace_min, b.pace_max):

            groups[-1].append(b)

        else:

            groups.append([b])

    phases = []

    for g in groups:

        first = g[0]

        tiros = first.kind == INTERVAL and len(g) >= 2

        dist = sum(b.executed_distance_m for b in g)

        dur = sum(b.executed_duration_sec for b in g)

        lo, hi = _pace_sec(first.pace_min), _pace_sec(first.pace_max)

        phases.append({
            "kind": "tiros" if tiros else "bloco",
            "label": f"{len(g)}× {_amount(first.planned_distance_m, first.planned_duration_sec)}".strip()
            if tiros else _total_amount(g),
            "target": _range(first.pace_min, first.pace_max) or None,
            "target_min_sec": min(v for v in (lo, hi) if v is not None) if (lo or hi) else None,
            "target_max_sec": max(v for v in (lo, hi) if v is not None) if (lo or hi) else None,
            "reps": [
                {
                    "pace_sec": round(b.executed_pace * 60) if b.executed_pace else None,
                    "ok": b.within_target,
                }
                for b in g
            ],
            "ok": sum(1 for b in g if b.within_target),
            "total": len(g),
            "avg_pace_sec": round(dur / (dist / 1000)) if dist > 0 else None,
        })

    return phases


def _garmin_phases(profile: str, date_iso: str, km: float, session) -> list[dict] | None:
    """Busca as voltas ROTULADAS da corrida no Garmin (lista recente → casa por
    data + km → typed splits) e pareia com os passos do plano. Síncrono (lib
    do Garmin) — chamar via asyncio.to_thread."""

    candidates = [
        a for a in GarminActivitySource.recent(profile, limit=40)
        if a.start_date.date().isoformat() == date_iso[:10]
        and abs(a.distance / 1000 - km) < 0.6
    ]

    if not candidates:

        return None

    act = min(candidates, key=lambda a: abs(a.distance / 1000 - km))

    typed = GarminClient.connect(profile).get_activity_typed_splits(act.id)

    blocks = GarminActivitySource._classify_splits(typed)

    cmp = PlannedExecutionMatcher.match(
        session, SimpleNamespace(raw={"_garmin_typed_blocks": blocks}),
    )

    return build_phases(cmp.blocks) if cmp else None


async def execution_phases(profile: str, date_iso: str, km: float, session) -> list[dict] | None:
    """Fases executadas pro card "Plano × feito" (cacheadas por corrida). None
    quando não dá: sem Garmin, treino sem passos, voltas não pareiam."""

    if session is None or not session.steps or not GarminClient.is_connected(profile):

        return None

    hit, cached = SharePhasesStore.get(profile, date_iso, km)

    if hit:

        return cached

    try:

        phases = await asyncio.to_thread(_garmin_phases, profile, date_iso, km, session)

    except Exception as e:

        # erro de rede/Garmin: NÃO guarda — tenta de novo na próxima
        print(f"share: voltas do Garmin falharam p/ '{profile}' {date_iso}: {e}")

        return None

    SharePhasesStore.put(profile, date_iso, km, phases)

    return phases


def _clean_quote(text: str) -> str:

    q = (text or "").strip().splitlines()[0] if (text or "").strip() else ""

    q = q.strip().strip('"“”\'').strip()

    if len(q) > QUOTE_MAX_CHARS:

        cut = q[:QUOTE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:")

        q = f"{cut}…"

    return q


def _fallback_quote(analysis: str) -> str | None:
    """Sem IA: 1ª frase do bloco "Análise" (tirando o vocativo "Fulano,")."""

    m = re.search(r"Análise\s*\n\s*•\s*(.+)", analysis or "")

    if not m:

        return None

    first = re.split(r"(?<=[.!?])\s", m.group(1).strip())[0]

    first = re.sub(r"^[A-ZÁÉÍÓÚ][\wáéíóúãõç]+,\s*", "", first)

    first = first[:1].upper() + first[1:]

    return _clean_quote(first) or None


async def coach_quote(profile: str, date_iso: str, km: float) -> str | None:
    """Frase curta do coach pro card "Coach diz". Guardada na análise depois
    da 1ª vez. None quando o treino ainda não foi analisado."""

    repo = WorkoutAnalysisRepository()

    entry = repo.find(profile, date_iso[:10], km)

    if entry is None or not entry.get("analysis"):

        return None

    if entry.get("share_quote"):

        return entry["share_quote"]

    quote = None

    try:

        raw = await generate_text(
            model=get_settings().gemini_extract_model,
            contents=QUOTE_PROMPT.format(
                analysis=entry["analysis"], max_chars=QUOTE_MAX_CHARS,
            ),
            config=types.GenerateContentConfig(
                max_output_tokens=120,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        quote = _clean_quote(raw) or None

    except Exception as e:

        print(f"Frase do coach (share) falhou p/ '{profile}': {e}")

    if quote:

        repo.annotate(profile, date_iso[:10], km, share_quote=quote)

        return quote

    # IA fora: frase determinística, NÃO guardada (tenta a IA de novo depois)
    return _fallback_quote(entry["analysis"])
