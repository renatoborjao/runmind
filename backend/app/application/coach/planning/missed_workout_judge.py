import json
from dataclasses import dataclass, field

from google.genai import types

from app.application.coach.planning.ai_session_builder import (
    build_session_dict,
)
from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import generate_text

_VALID_DAYS = set(WEEKDAYS.values())

MAX_OUTPUT_TOKENS = 1600

PROMPT_TEMPLATE = """Você é o treinador de corrida do RunMind. O atleta \
{runner_name} NÃO fez o treino de ontem. Meta: {objective}.

TREINO QUE FUROU (ontem, {missed_label}): {missed_type}, {missed_distance}.

PLANO DESTA SEMANA:
{sessions}

Execução até agora nesta semana: cumpriu {done} de {total} treinos.

RETRATO REAL DO ATLETA (histórico e evolução — a base da sua decisão):
{portrait}

DECIDA, como treinador, usando o retrato acima:

- Se o furo NÃO atrapalha a evolução (treino absorvível, ele vem consistente):
  apenas TRANQUILIZE. A "message" diz que viu que ontem não rolou e que o plano
  SEGUE O MESMO, sem prejuízo. "operations" fica VAZIO.

- Se o furo IMPORTA (mexe na evolução): REAVALIE os próximos dias da semana com
  base no histórico e na evolução dele. Você NÃO é obrigado a repetir nem
  remanejar o treino que furou — decida o que serve melhor à evolução e à meta:
  pode trocar o tipo, redistribuir o estímulo, ajustar volume, ou o que fizer
  sentido. Toda a inteligência é sua, ancorada no retrato. Preencha
  "operations" e a "message" TERMINA perguntando se pode aplicar.

"operations": mudanças só de HOJE em diante, cada uma:
  {{"action": "replace", "day": "Thursday", "session": {{ ...sessão nova... }}}}
  {{"action": "drop", "day": "Friday"}}
Sessão nova em "replace": workout_type, distance_km, pace_min, pace_max,
purpose, structure (lista de passos em texto) e steps (estruturado: kind
warmup/interval/recovery/cooldown/repeat, com distance_m/distance_km ou
duration_min, e pace_min/pace_max). Mesma modalidade do dia.

Responda APENAS JSON. Furo sem impacto:
{{"impact": "low",
  "message": "Vi que o treino de ontem não rolou — tranquilo, seu plano segue \
o mesmo, não atrapalha sua evolução. 💪",
  "operations": []}}

Furo que importa:
{{"impact": "meaningful",
  "message": "Vi que você não fez o treino de ontem. Dá pra reorganizar seus \
próximos dias pra manter a evolução — quer que eu ajuste?",
  "operations": [ ... ]}}

Sem markdown. Tom de WhatsApp, curto e humano — nunca culpando o atleta.
"""


@dataclass(slots=True)
class MissedJudgment:

    message: str

    # vazio = só informar (plano segue igual); com itens = proposta a aplicar
    operations: list[dict] = field(default_factory=list)


class MissedWorkoutJudge:
    """IA-treinadora: dado o furo de ontem e o RETRATO real do atleta, decide
    se o plano segue igual (só tranquiliza) ou se vale reorganizar os próximos
    dias — e, nesse caso, monta o re-plano livremente (não repete o treino
    furado). Nada é aplicado aqui: vira proposta pro 'sim'."""

    @staticmethod
    async def judge(
        runner: RunnerProfile,
        plan: TrainingPlan,
        missed: PlannedSession,
        done: int,
        total: int,
        portrait: str,
    ) -> MissedJudgment | None:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner.name,
            objective=plan.objective or runner.goal,
            missed_label=weekday_label(missed.day),
            missed_type=missed.workout_type,
            missed_distance=(
                f"{missed.planned_distance_km:.0f}km"
                if missed.planned_distance_km
                else "sem distância"
            ),
            sessions=MissedWorkoutJudge._render_sessions(plan),
            done=done,
            total=total,
            portrait=portrait or "(sem retrato disponível)",
        )

        raw = await generate_text(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            require_text=True,
        )

        return MissedWorkoutJudge._parse(raw, plan)

    @staticmethod
    def _render_sessions(plan: TrainingPlan) -> str:

        lines = []

        for session in plan.sessions:

            distance = (
                f"{session.planned_distance_km:.0f}km"
                if session.planned_distance_km
                else "s/ distância"
            )

            lines.append(
                f"- {weekday_label(session.day)} ({session.day}): "
                f"{session.workout_type}, {distance}"
            )

        return "\n".join(lines) or "(sem sessões)"

    @staticmethod
    def _parse(raw: str, plan: TrainingPlan) -> MissedJudgment | None:

        try:

            data = json.loads(raw)

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict):

            return None

        message = str(data.get("message", "")).strip()

        if not message:

            return None

        operations = MissedWorkoutJudge._valid_operations(
            data.get("operations"),
            plan,
        )

        return MissedJudgment(message=message, operations=operations)

    @staticmethod
    def _valid_operations(raw, plan: TrainingPlan) -> list[dict]:
        """Só operações bem formadas e em dias válidos entram; a sessão nova
        é mapeada pro formato da PlannedSession (o applier a reidrata). O que
        vier torto é descartado — nada quebra na hora de aplicar."""

        if not isinstance(raw, list):

            return []

        valid = []

        for op in raw:

            if not isinstance(op, dict) or op.get("day") not in _VALID_DAYS:

                continue

            day = op["day"]

            if op.get("action") == "drop":

                valid.append({"action": "drop", "day": day})

            elif op.get("action") == "replace" and isinstance(
                op.get("session"), dict
            ):

                existing = plan.find_session_by_day(day)

                kind = existing.kind if existing else "run"

                session = build_session_dict(day, kind, op["session"])

                if session is not None:

                    valid.append(
                        {"action": "replace", "day": day, "session": session}
                    )

        return valid
