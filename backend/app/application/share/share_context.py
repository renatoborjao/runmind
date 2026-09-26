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

import re
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from google.genai import types

from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.config import get_settings
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import generate_text
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
    """Sessão do plano que a corrida (data + km) cumpriu, ou None (treino
    extra, sem plano naquela semana, plano de treinador sem casamento)."""

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

    return {
        "workout_type": session.workout_type,
        "distance_km": session.planned_distance_km,
        "pace_min": session.target_pace_min,
        "pace_max": session.target_pace_max,
        "duration_min": session.planned_duration_minutes,
    }


def period_goal_km(profile: str, start: date, end: date) -> float | None:
    """Meta de km do período = soma das sessões planejadas (com distância)
    cujas datas caem em [start, end]. None quando não há plano no período."""

    total = 0.0

    found = False

    for plan in _plans(profile):

        for session in plan.sessions:

            try:

                d = plan.session_date(session)

            except Exception:

                continue

            if start <= d <= end and (session.planned_distance_km or 0) > 0:

                total += session.planned_distance_km

                found = True

    return round(total, 1) if found else None


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
