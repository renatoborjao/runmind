import json
from dataclasses import dataclass

from google.genai import types

from app.application.coach.planning.ai_session_builder import (
    build_session_dict,
)
from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS, weekday_label
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

VALID_DAYS = set(WEEKDAYS.values())

MAX_OUTPUT_TOKENS = 1400

PROMPT_TEMPLATE = """Você é o treinador de corrida do RunMind. O atleta \
{runner_name} mandou uma mensagem que PODE ser um pedido pra evitar/trocar um \
tipo de treino da semana dele. Meta: {objective}.

PLANO DESTA SEMANA (dias de corrida):
{sessions}

MENSAGEM DO ATLETA:
"{message}"

Decida:
1) A mensagem é um pedido pra NÃO fazer / trocar um tipo de treino? Se NÃO for
   (é dúvida, elogio, outro assunto), responda {{"found": false}} e pare.
2) Se for, escolha a sessão do plano que ele quer mudar (o "day" em inglês) e
   classifique o motivo:
   - "chatice" (gosto/tédio): MANTENHA o estímulo fisiológico e troque só a
     FORMA (ex.: fartlek na rua no lugar de tiro na pista; progressivo no
     lugar de tempo em ritmo fixo). Mesma distância aproximada e mesmo dia.
   - "restricao" (dor/limite físico): troque por um treino seguro que evite o
     gesto que incomoda, compensando o objetivo como der.
   - "medo" (insegurança): proponha uma versão mais gentil do MESMO estímulo
     (dose menor), não remova.
3) Monte a sessão SUBSTITUTA no mesmo dia e mesma modalidade, ancorada nos
   paces da meta.

Responda APENAS JSON:
{{"found": true,
  "day": "Tuesday",
  "reason": "chatice",
  "session": {{
    "workout_type": "Fartlek",
    "distance_km": 9.0,
    "pace_min": "4:45", "pace_max": "5:30",
    "purpose": "manter o estímulo de velocidade sem a pista",
    "structure": ["Aquecimento: 2 km leve",
      "8x (1 min forte / 1 min trote) na rua",
      "Desaquecimento: 1,5 km leve"],
    "steps": [
      {{"kind": "warmup", "distance_km": 2, "pace_min": "6:30", "pace_max": "7:00"}},
      {{"kind": "repeat", "reps": 8, "steps": [
        {{"kind": "interval", "duration_min": 1, "pace_min": "4:45", "pace_max": "5:00"}},
        {{"kind": "recovery", "duration_min": 1}}
      ]}},
      {{"kind": "cooldown", "distance_km": 1.5, "pace_min": "6:30", "pace_max": "7:00"}}
    ]
  }},
  "message": "mensagem curta de WhatsApp: reconhece o que ele falou, explica a \
troca (mantendo o objetivo) e TERMINA perguntando se pode aplicar. Sem \
markdown."}}

Se a mudança conflitar com a meta (ex.: odeia longão treinando pra 21k), NÃO
obedeça cego: proponha um MEIO-TERMO na "session" e explique o trade-off na
"message" (tom de treinador que negocia, não que só acata).
"""


@dataclass(slots=True)
class AversionSwap:

    day: str

    # sessão substituta pronta pra virar operação de proposta (replace)
    session: dict

    # texto que o atleta vê: explica a troca e pergunta se aplica
    message: str


class AversionSwapEngine:
    """IA-treinadora: dado o pedido do atleta e o plano da semana, decide se
    é uma aversão e monta a sessão substituta (mantendo o estímulo). Devolve
    None quando não é um pedido claro de troca."""

    @staticmethod
    async def propose(
        runner: RunnerProfile,
        plan: TrainingPlan,
        incoming_text: str,
    ) -> AversionSwap | None:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner.name,
            objective=plan.objective or runner.goal,
            sessions=AversionSwapEngine._render_sessions(plan),
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
            parse=lambda raw: AversionSwapEngine._parse(raw, plan),
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
                + (f" — {session.purpose}" if session.purpose else "")
            )

        return "\n".join(lines) or "(sem sessões de corrida)"

    @staticmethod
    def _parse(raw: str, plan: TrainingPlan) -> AversionSwap | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict) or not data.get("found"):

            return None

        day = data.get("day")

        if day not in VALID_DAYS:

            return None

        target = plan.find_session_by_day(day)

        if target is None:

            return None

        raw_session = data.get("session")

        message = str(data.get("message", "")).strip()

        if not isinstance(raw_session, dict) or not message:

            return None

        session = build_session_dict(day, target.kind, raw_session)

        if session is None:

            return None

        return AversionSwap(day=day, session=session, message=message)
