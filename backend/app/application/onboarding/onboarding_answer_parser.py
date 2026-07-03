import json

from google import genai
from google.genai import types

from app.core.config import get_settings

DEFAULT_MODEL = "gemini-2.5-flash"

MAX_OUTPUT_TOKENS = 300

# O que extrair em cada passo do questionário.
STEP_INSTRUCTIONS = {
    "ASK_NAME": (
        'Extraia o primeiro nome (ou apelido) do corredor.\n'
        'Formato: {"name": "..."}'
    ),
    "ASK_BODY": (
        'Extraia idade (anos, int), peso (kg, número) e altura '
        '(metros, número — "1,78" ou "178cm" viram 1.78).\n'
        'Formato: {"age": 33, "weight": 91.0, "height": 1.78}'
    ),
    "ASK_STRAVA": (
        'O corredor usa Strava?\n'
        'Formato: {"has_strava": true}'
    ),
    "ASK_EXPERIENCE": (
        'O corredor já corre hoje? Se sim, quantas vezes por semana e '
        'quantos km por treino (números).\n'
        'Formato: {"runs_today": true, "runs_per_week": 3, '
        '"typical_km": 5.0} — se não corre: {"runs_today": false}'
    ),
    "ASK_PACE": (
        'Extraia o tempo que o corredor leva na distância habitual, em '
        'minutos totais (número — "32 minutos" vira 32, "meia hora" '
        'vira 30).\n'
        'Formato: {"typical_minutes": 32.0}'
    ),
    "ASK_DAYS": (
        'Extraia os dias da semana em que o corredor pode correr, em '
        'inglês capitalizado (Monday..Sunday).\n'
        'Formato: {"days": ["Tuesday", "Thursday", "Saturday"]}'
    ),
    "ASK_GOAL": (
        'Extraia o objetivo do corredor: descrição curta e, se houver, '
        'distância alvo (km) e tempo alvo (HH:MM:SS).\n'
        'Formato: {"goal": "10 km Sub 55", "target_race": "10 km", '
        '"target_time": "00:55:00"} — campos sem informação: null'
    ),
    "CONFIRM": (
        'O corredor confirmou que quer o plano?\n'
        'Formato: {"confirmed": true}'
    ),
}

PROMPT_TEMPLATE = """Você interpreta respostas do questionário de \
cadastro do RunMind (coach de corrida via WhatsApp, pt-BR).

PERGUNTA FEITA AO CORREDOR:
{question}

TAREFA DE EXTRAÇÃO:
{instruction}

RESPOSTA DO CORREDOR:
{answer}

Responda APENAS com o JSON pedido. Se a resposta não contiver a
informação pedida (ou for ambígua), responda {{}} (objeto vazio).
Não invente valores.
"""


class OnboardingAnswerParser:

    @staticmethod
    async def parse(
        step: str,
        question: str,
        answer: str,
    ) -> dict:

        instruction = STEP_INSTRUCTIONS.get(step)

        if instruction is None:

            return {}

        settings = get_settings()

        client = genai.Client(
            api_key=settings.google_api_key,
        )

        prompt = PROMPT_TEMPLATE.format(
            question=question,
            instruction=instruction,
            answer=answer,
        )

        response = await client.aio.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                # extração estruturada não precisa de raciocínio; com
                # thinking ligado os tokens de pensamento estouram o
                # max_output_tokens e o JSON volta vazio (flaky)
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        return OnboardingAnswerParser._parse_json(
            response.text or "",
        )

    @staticmethod
    def _parse_json(
        raw: str,
    ) -> dict:

        try:

            data = json.loads(raw)

        except (json.JSONDecodeError, TypeError):

            return {}

        if not isinstance(data, dict):

            return {}

        return data
