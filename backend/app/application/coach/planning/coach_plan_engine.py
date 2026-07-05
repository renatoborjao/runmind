import json
from datetime import date

from google.genai import types

from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import generate_text

MAX_OUTPUT_TOKENS = 2000

VALID_DAYS = set(WEEKDAYS.values())

# só planejamos corrida/caminhada; musculação, descanso, bike etc. NÃO são
# nossos — o atleta cuida disso. Se a IA devolver, a gente descarta.
RUNNING_KINDS = {"run", "walk", "run_walk"}

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente montando o plano \
da PRÓXIMA SEMANA para um atleta específico. O plano tem que ser REAL e VIVO:
segue a evolução, os limites e a rotina que já funcionam para ELE — nada de
fórmula genérica nem de inflar volume.

RETRATO REAL DO ATLETA (dados do histórico dele — use só isto, não invente):
{context}

REGRAS:
- O plano é SÓ de corrida/caminhada. NÃO prescreva musculação, descanso, bike
  ou qualquer outra atividade — isso não é seu (o atleta cuida por conta).
  Apenas as sessões de corrida/caminhada nos dias de corrida dele.
- Respeite a FREQUÊNCIA de corrida que funciona para ele (não adicione dias só
  para "encher"). Se ele responde bem a N corridas por semana, mantenha N.
- NÃO aumente o volume sem motivo. Progrida com critério, seguindo a evolução
  real e a aderência das últimas semanas; segure ou recue se ele não vem
  cumprindo.
- Cada corrida com um PROPÓSITO distinto (velocidade, base/rodagem, longão,
  regenerativo...), com estrutura concreta (aquecimento, séries, strides,
  fechamento) e faixa de pace ancorada na META dele.
- Respeite lesões/limitações e preferências que aparecerem no retrato.

Responda APENAS com JSON:
{{"weekly_objective": "objetivo/foco curto da semana",
  "sessions": [
    {{"day": "Tuesday", "kind": "run", "workout_type": "Velocidade",
      "distance_km": 9.0, "pace_min": "4:45", "pace_max": "4:50",
      "structure": "Aquecimento 2 km + 6x800m (rec 400m trote) + 1,5 km leve",
      "purpose": "aumentar o ritmo de prova"}}
  ]}}

Cada sessão é uma corrida/caminhada com distance_km, paces, structure e
purpose. kind: "run" (corrida) ou "walk"/"run_walk" (caminhada/corrida-
caminhada, iniciante). Use os dias da semana em inglês (Monday..Sunday).
"""


class CoachPlanEngine:
    """IA-treinadora: gera o plano da semana a partir do retrato real do
    atleta. Se falhar, o chamador cai no motor determinístico (fallback)."""

    @staticmethod
    async def generate(
        runner_name: str,
        objective: str,
        week_start: date,
        context: str,
    ) -> TrainingPlan:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(context=context)

        raw = await generate_text(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
            require_text=True,
        )

        return CoachPlanEngine._to_plan(
            raw,
            runner_name,
            objective,
            week_start,
        )

    @staticmethod
    def _to_plan(
        raw: str,
        runner_name: str,
        objective: str,
        week_start: date,
    ) -> TrainingPlan:

        try:

            data = json.loads(raw)

        except (json.JSONDecodeError, TypeError) as e:

            raise ValueError(f"JSON do plano inválido: {e}")

        if not isinstance(data, dict):

            raise ValueError("plano da IA não é um objeto")

        sessions = CoachPlanEngine._parse_sessions(
            data.get("sessions", []),
        )

        if not any(s.kind == "run" for s in sessions):

            raise ValueError("plano da IA sem corridas")

        running_days = [s.day for s in sessions if s.kind == "run"]

        weekly_volume = round(
            sum(s.planned_distance_km or 0 for s in sessions),
            1,
        )

        return TrainingPlan(
            athlete_name=runner_name,
            objective=objective,
            phase="IA",
            weekly_volume=weekly_volume,
            running_days=running_days,
            week_start=week_start,
            sessions=sessions,
            weekly_objective=str(data.get("weekly_objective", "")).strip(),
        )

    @staticmethod
    def _parse_sessions(raw_sessions) -> list[PlannedSession]:

        if not isinstance(raw_sessions, list):

            return []

        sessions = []

        for item in raw_sessions:

            if not isinstance(item, dict):

                continue

            day = item.get("day")

            if day not in VALID_DAYS:

                continue

            kind = item.get("kind", "run")

            # descarta musculação/descanso/bike — não planejamos isso
            if kind not in RUNNING_KINDS:

                continue

            distance = item.get("distance_km")

            if not isinstance(distance, (int, float)) or distance <= 0:

                distance = None

            sessions.append(
                PlannedSession(
                    day=day,
                    workout_type=(
                        item.get("workout_type")
                        or CoachPlanEngine._default_type(kind)
                    ),
                    objective=str(item.get("purpose", "")).strip(),
                    planned_distance_km=(
                        round(float(distance), 1)
                        if distance is not None
                        else None
                    ),
                    planned_duration_minutes=None,
                    target_pace_min=CoachPlanEngine._pace(item.get("pace_min")),
                    target_pace_max=CoachPlanEngine._pace(item.get("pace_max")),
                    kind=kind,
                    structure=str(item.get("structure", "")).strip(),
                    purpose=str(item.get("purpose", "")).strip(),
                )
            )

        return sessions

    @staticmethod
    def _default_type(kind: str) -> str:

        return {
            "walk": "Caminhada",
            "run_walk": "Corrida-caminhada",
        }.get(kind, "Corrida")

    @staticmethod
    def _pace(value) -> str | None:

        if not value:

            return None

        return str(value).strip()
