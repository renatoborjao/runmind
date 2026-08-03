import json
from dataclasses import dataclass

from google.genai import types

from app.application.coach.planning.ai_session_builder import (
    build_session_dict,
)
from app.application.coach.planning.workout_menu import (
    PHASE_EMPHASIS,
    TIME_OR_DISTANCE_RULE,
    WORKOUT_MENU,
)
from app.core.config import get_settings
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 1600


PROMPT_TEMPLATE = """Você é o treinador de corrida do Ritmind. O atleta \
{runner_name} pediu que VOCÊ monte um treino AVULSO pra um dia específico que o \
plano dele não cobre. Meta: {objective}.

DIA ALVO: {target_label}.

O QUE JÁ EXISTE NA SEMANA DELE (não repita à toa, COMPLEMENTE):
{week_context}

RETRATO REAL DO ATLETA (histórico e evolução — a base da sua decisão):
{portrait}

Monte UM treino só pra o dia alvo, como treinador de verdade:
- ANCORE tudo no retrato real (volume, paces, evolução) — nada genérico.
- COMPLEMENTE a semana: não empilhe dois dias fortes coladinhos; se ele já \
teve/terá carga forte perto, faça um dia de absorver (rodagem/regenerativo); se \
a semana está leve, este é o dia de ENTREGAR o estímulo que falta rumo à meta.
- ESCOLHA O TIPO CERTO com EXPERTISE — NÃO caia sempre na rodagem leve por \
segurança. Você tem um LEQUE de estímulos; pegue o que a semana e a fase pedem:
{menu}
  QUANDO usar: {phase}. Se a semana já cobre a qualidade que a meta pede e o dia \
é de absorver carga, aí sim rodagem/regenerativo. Mas quando FALTA qualidade \
rumo à meta, traga a qualidade certa (um tempo de limiar, um fartlek, um \
intervalado) — não um trote genérico "por garantia".
- AVERSÃO: se o retrato disser que ele não gosta de um tipo, mantenha o \
estímulo e troque só a FORMA (fartlek na rua no lugar de tiro na pista); só \
remova de verdade se for dor/restrição física.
- {time_rule}
- Respeite saúde, recuperação e lesões. Dose o volume pelo que ele SUSTENTA hoje.

Responda APENAS JSON (o "session" abaixo é só de FORMATO — escolha o tipo pela \
semana/fase/meta, NÃO copie "Rodagem leve"):
{{"message": "mensagem curta de WhatsApp: apresenta o treino e explica em 1 \
frase por que ESSE treino nesse dia (o encaixe na semana). Sem markdown (no \
máximo • e um *negrito*). NÃO pergunte se pode aplicar.",
  "session": {{
    "workout_type": "Rodagem leve",
    "distance_km": 8.0,
    "pace_min": "6:00", "pace_max": "6:30",
    "structure": ["Aquecimento: corpo solto", "8 km confortáveis, dá pra \
conversar", "Foco: base aeróbica sem forçar"],
    "steps": [
      {{"kind": "run", "distance_km": 8, "pace_min": "6:00", "pace_max": "6:30"}}
    ],
    "purpose": "base aeróbica complementando a semana"}}
}}
Sessão POR TEMPO: troque "distance_km": 8.0 por "duration_min": 50 (fica sem km)
e use "duration_min" nos steps.
"""


@dataclass(slots=True)
class OneOffWorkout:

    # sessão pronta pro formato PlannedSession (o repositório/applier reidrata)
    session: dict

    # texto que o atleta vê: apresenta o treino e o porquê do encaixe
    message: str


class OneOffWorkoutEngine:
    """IA-treinadora: monta UMA sessão avulsa pra um dia que o plano não cobre,
    ancorada no retrato real do atleta e complementar ao que já existe na
    semana. Devolve None quando a IA não produz um treino utilizável."""

    @staticmethod
    async def build(
        runner: RunnerProfile,
        objective: str,
        target_day: str,
        target_label: str,
        portrait: str,
        week_context: str,
    ) -> OneOffWorkout | None:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            runner_name=runner.name,
            objective=objective or runner.goal or "saúde e evolução",
            target_label=target_label,
            week_context=week_context or "(nada registrado nesta semana)",
            portrait=portrait or "(sem retrato disponível)",
            menu=WORKOUT_MENU,
            phase=PHASE_EMPHASIS,
            time_rule=TIME_OR_DISTANCE_RULE,
        )

        return await generate_json(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=lambda raw: OneOffWorkoutEngine._parse(raw, target_day),
        )

    @staticmethod
    def _parse(raw: str, target_day: str) -> OneOffWorkout | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict):

            return None

        message = str(data.get("message", "")).strip()

        raw_session = data.get("session")

        if not message or not isinstance(raw_session, dict):

            return None

        session = build_session_dict(target_day, "run", raw_session)

        if session is None:

            return None

        # marca a origem: treino nosso, avulso — empurrado e reconhecido à parte
        session["origin"] = "oneoff"

        return OneOffWorkout(session=session, message=message)
