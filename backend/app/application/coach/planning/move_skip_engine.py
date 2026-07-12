import json
from dataclasses import dataclass
from datetime import date

from google.genai import types

from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label, weekday_name
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

VALID_DAYS = set(WEEKDAYS.values())

MAX_OUTPUT_TOKENS = 500

PROMPT_TEMPLATE = """Você é o treinador de corrida do RunMind. O atleta \
{runner_name} mandou uma mensagem que PODE ser um pedido pra MOVER um treino \
de dia ou PULAR (não fazer) um treino desta semana.

Hoje é {today}.

PLANO DESTA SEMANA (dias de corrida):
{sessions}

MENSAGEM DO ATLETA:
"{message}"

Decida a AÇÃO:
- "skip": ele NÃO vai fazer um treino (quer pular/dropar). Ache o "day" (em
  inglês) da sessão. "hoje"/"amanhã" resolvem pela data de hoje. Se o dia
  citado não tem treino planejado, use "none".
- "move": ele quer fazer um treino em OUTRO dia. Ache o "day" (origem, em
  inglês) e o "target_day" (destino, em inglês). O destino deve ser um dia
  SEM treino planejado.
- "none": não é pedido de mover nem pular (dúvida, elogio, outro assunto).

Se for MOVE e o destino colar dois treinos puxados em dias seguidos, AVISE na
"message" (proponha, mas sinalize o trade-off — tom de treinador que cuida,
não que só obedece).

Responda APENAS JSON. Pular:
{{"action": "skip", "day": "Tuesday",
  "message": "mensagem curta de WhatsApp: reconhece, confirma o que vai fazer \
(tirar o treino de terça) e TERMINA perguntando se pode aplicar. Sem markdown."}}

Mover:
{{"action": "move", "day": "Tuesday", "target_day": "Wednesday",
  "message": "..."}}

Nenhum:
{{"action": "none"}}
"""


@dataclass(slots=True)
class MoveSkipRequest:

    action: str            # "move" | "skip"

    day: str               # dia de origem (inglês)

    target_day: str | None  # destino (inglês), só no "move"

    message: str


class MoveSkipEngine:
    """IA-treinadora: entende o pedido de mover/pular um treino da semana e
    devolve a ação estruturada. Nada é aplicado aqui — vira proposta pro 'sim'.
    Devolve None quando não é um pedido claro de mover/pular."""

    @staticmethod
    async def propose(
        runner: RunnerProfile,
        plan: TrainingPlan,
        incoming_text: str,
        today: date,
    ) -> MoveSkipRequest | None:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner.name,
            today=(
                f"{weekday_label(weekday_name(today))}, "
                f"{today.strftime('%d/%m/%Y')}"
            ),
            sessions=MoveSkipEngine._render_sessions(plan),
            message=incoming_text.replace('"', "'"),
        )

        return await generate_json(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=lambda raw: MoveSkipEngine._parse(raw, plan),
        )

    @staticmethod
    def _render_sessions(plan: TrainingPlan) -> str:

        lines = []

        for session in plan.sessions:

            if session.kind not in {"run", "walk", "run_walk"}:

                continue

            distance = (
                f"{session.planned_distance_km:.0f}km"
                if session.planned_distance_km
                else "s/ distância"
            )

            lines.append(
                f"- {weekday_label(session.day)} ({session.day}): "
                f"{session.workout_type}, {distance}"
            )

        return "\n".join(lines) or "(sem sessões de corrida)"

    @staticmethod
    def _parse(raw: str, plan: TrainingPlan) -> MoveSkipRequest | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict):

            return None

        action = data.get("action")

        message = str(data.get("message", "")).strip()

        if action not in {"move", "skip"} or not message:

            return None

        day = data.get("day")

        # precisa haver uma sessão nesse dia pra mover/pular
        if day not in VALID_DAYS or plan.find_session_by_day(day) is None:

            return None

        target_day = None

        if action == "move":

            target_day = data.get("target_day")

            if target_day not in VALID_DAYS or target_day == day:

                return None

            # v1: só move pra dia LIVRE — senão o replace apagaria o treino
            # do destino (swap fica pra depois)
            if plan.find_session_by_day(target_day) is not None:

                return None

        return MoveSkipRequest(
            action=action,
            day=day,
            target_day=target_day,
            message=message,
        )
