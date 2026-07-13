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

RUNNING_KINDS = {"run", "walk", "run_walk"}

# semana ajustada inteira -> saída grande; Pro pensa (thinking conta no
# orçamento). Teto explícito de thinking + max_output com folga (senão volta
# vazio). Mesmos números do plano.
THINKING_BUDGET = 1024

# Folga generosa pra o JSON da semana ajustada + thinking do Pro caberem sem
# CORTE (JSON cortado = principal causa de quebra e de retry PAGO). Só paga o
# que gera, não o teto — a folga é de graça e derruba os retries.
MAX_OUTPUT_TOKENS = 6000

PROMPT_TEMPLATE = """Você é o treinador de corrida do RunMind. O atleta \
{runner_name} mandou uma mensagem que PODE ser um pedido pra AJUSTAR o plano \
da semana (deixar mais leve/pesado, mais rodagens, menos intensidade, mudar a \
carga/distribuição...). Meta dele: {objective}.

PLANO DESTA SEMANA (dias de corrida — respeite a MESMA frequência/dias):
{sessions}

MENSAGEM DO ATLETA:
"{message}"

Decida:
1) É um pedido pra AJUSTAR o plano da semana? Se NÃO for (dúvida, elogio, outro
   assunto, ou só reclamar sem pedir mudança), responda {{"adjust": false}} e
   pare.
2) Se for, você é MALEÁVEL MAS COM CRITÉRIO — igual treinador de verdade:
   - ATENDA o pedido no que for seguro e razoável (reduzir/aumentar carga,
     trocar a forma de um treino, redistribuir).
   - MAS SEGURE O ESSENCIAL rumo à meta: não jogue fora o estímulo que a meta
     exige. Se o pedido conflita com o objetivo, faça um MEIO-TERMO e explique
     o trade-off (nunca só obedeça, nunca só recuse).
   - Mantenha os MESMOS dias/frequência do atleta (não adicione nem remova dias
     sem ele pedir). Ancore os paces na meta.
3) Devolva a SEMANA INTEIRA já ajustada (todas as sessões de corrida dos dias
   dele), mesmo as que não mudaram.

Responda APENAS JSON:
{{"adjust": true,
  "message": "mensagem curta de WhatsApp: reconhece o pedido e resume o que \
mudou e por que segurou o essencial rumo à meta. NÃO pergunte se pode aplicar \
(o sistema mostra a semana revisada e pergunta depois). Sem markdown (use no \
máximo • e um *negrito*).",
  "sessions": [
    {{"day": "Tuesday", "workout_type": "Rodagem leve", "distance_km": 6.0,
      "pace_min": "6:00", "pace_max": "6:30",
      "structure": ["Aquecimento: já no ritmo, corpo solto",
        "6 km confortáveis, dá pra conversar",
        "Foco: base aeróbica sem forçar"],
      "steps": [
        {{"kind": "run", "distance_km": 6, "pace_min": "6:00", "pace_max": "6:30"}}
      ],
      "purpose": "aliviar a carga mantendo a base"}}
  ]}}
"""


@dataclass(slots=True)
class Negotiation:

    # operações prontas pra virar proposta (replace por dia + drop dos removidos)
    operations: list[dict]

    # texto que o atleta vê: explica o ajuste e pergunta se aplica
    message: str


class NegotiationEngine:
    """IA-treinadora: dado o pedido de ajuste do atleta e o plano da semana,
    remonta a semana MALEÁVEL MAS COM CRITÉRIO (segura o essencial da meta).
    Devolve None quando não é um pedido de ajuste claro."""

    @staticmethod
    async def propose(
        runner: RunnerProfile,
        plan: TrainingPlan,
        incoming_text: str,
    ) -> Negotiation | None:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner.name,
            objective=plan.objective or runner.goal,
            sessions=NegotiationEngine._render_sessions(plan),
            message=incoming_text.replace('"', "'"),
        )

        return await generate_json(
            model=settings.gemini_coach_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=THINKING_BUDGET,
                ),
            ),
            parse=lambda raw: NegotiationEngine._parse(raw, plan),
        )

    @staticmethod
    def _render_sessions(plan: TrainingPlan) -> str:

        lines = []

        for session in plan.sessions:

            if session.kind not in RUNNING_KINDS:

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
    def _parse(raw: str, plan: TrainingPlan) -> Negotiation | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict) or not data.get("adjust"):

            return None

        message = str(data.get("message", "")).strip()

        raw_sessions = data.get("sessions")

        if not message or not isinstance(raw_sessions, list):

            return None

        # modalidade (run/walk/run_walk) de cada dia vem do plano atual —
        # a negociação ajusta a carga, não muda um corredor em caminhante
        kind_by_day = {
            session.day.lower(): session.kind for session in plan.sessions
        }

        operations: list[dict] = []

        new_days: set[str] = set()

        for item in raw_sessions:

            if not isinstance(item, dict):

                continue

            day = item.get("day")

            if day not in VALID_DAYS:

                continue

            kind = kind_by_day.get(day.lower(), "run")

            session = build_session_dict(day, kind, item)

            if session is None:

                continue

            operations.append(
                {"action": "replace", "day": day, "session": session}
            )

            new_days.add(day.lower())

        if not operations:

            return None

        # dia de corrida que sumiu da semana ajustada -> drop explícito
        for session in plan.sessions:

            if (
                session.kind in RUNNING_KINDS
                and session.day.lower() not in new_days
            ):

                operations.append({"action": "drop", "day": session.day})

        return Negotiation(operations=operations, message=message)
