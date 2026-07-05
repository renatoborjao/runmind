import json

from google.genai import types

from app.application.onboarding.deterministic_onboarding_parser import (
    DeterministicOnboardingParser,
)
from app.core.clock import today_local
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import generate_text

MAX_OUTPUT_TOKENS = 300

# O que extrair em cada passo do questionário.
STEP_INSTRUCTIONS = {
    "ASK_NAME": (
        'Extraia o primeiro nome (ou apelido) do corredor.\n'
        'Formato: {"name": "..."}'
    ),
    "ASK_AGE": (
        'Extraia a idade do corredor em anos (int).\n'
        'Formato: {"age": 33}'
    ),
    "ASK_WEIGHT": (
        'Extraia o peso do corredor em kg (número).\n'
        'Formato: {"weight": 91.0}'
    ),
    "ASK_HEIGHT": (
        'Extraia a altura do corredor em metros (número — "1,78" ou '
        '"178cm" viram 1.78).\n'
        'Formato: {"height": 1.78}'
    ),
    "ASK_STRAVA": (
        'O corredor já tem conta no Strava?\n'
        'Formato: {"has_strava": true}'
    ),
    "ASK_RUNS_TODAY": (
        'O corredor já corre hoje?\n'
        'Formato: {"runs_today": true} — se não corre: '
        '{"runs_today": false}'
    ),
    "ASK_RUNS_PER_WEEK": (
        'Extraia quantas vezes por semana o corredor costuma correr '
        '(int, 1 a 7).\n'
        'Formato: {"runs_per_week": 3}'
    ),
    "ASK_TYPICAL_KM": (
        'Extraia quantos km o corredor costuma fazer por treino '
        '(número).\n'
        'Formato: {"typical_km": 5.0}'
    ),
    "ASK_MOVEMENT": (
        'O corredor ainda não corre. Classifique como ele se move hoje: '
        '"walker" (só caminha), "run_walker" (alterna trote e caminhada) '
        'ou "runner" (já corre contínuo, mesmo que pouco). Extraia também, '
        'se houver, quantos minutos corre sem parar (continuous_run_minutes) '
        'e a velocidade de caminhada em km/h (walk_speed_kmh).\n'
        'Formato: {"mobility": "run_walker", "continuous_run_minutes": 1, '
        '"walk_speed_kmh": 5.5} — campos sem info: null'
    ),
    "ASK_COACH": (
        'O corredor já treina com um treinador ou segue uma planilha?\n'
        'Formato: {"has_coach": true}'
    ),
    "AWAIT_PLAN_MEDIA": (
        'O corredor disse que vai mandar o plano de treino depois '
        '(ex: "mando depois", "não tenho agora", "mais tarde")?\n'
        'Formato: {"skip": true} — qualquer outra coisa: {}'
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
        'distância alvo (km), tempo alvo (HH:MM:SS) e data da prova '
        '(ISO; sem dia exato, use o dia 15 do mês citado).\n'
        'Formato: {"goal": "10 km Sub 55", "target_race": "10 km", '
        '"target_time": "00:55:00", "race_date": "2026-08-15"} — '
        'campos sem informação: null'
    ),
    "CONFIRM": (
        'O corredor confirmou que quer o plano?\n'
        'Formato: {"confirmed": true}'
    ),
    "ASK_WEEK_CHOICE": (
        'O corredor quer começar o plano NESTA semana (atual) ou só na '
        'PRÓXIMA? "esta/essa/atual/agora/já/nesta/pode ser essa" = '
        'current; "próxima/semana que vem/segunda/depois/próxima semana" '
        '= next.\n'
        'Formato: {"start_week": "current"} ou {"start_week": "next"}'
    ),
}

PROMPT_TEMPLATE = """Você interpreta respostas do questionário de \
cadastro do RunMind (coach de corrida via WhatsApp, pt-BR).

Hoje é {today} (use para resolver datas relativas como "em agosto").

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

        # Determinístico primeiro: "sim", "terça e quinta", "33 anos..."
        # não precisam do Gemini — e assim não há como "me embananar".
        local = DeterministicOnboardingParser.parse(step, answer)

        if local is not None:

            return local

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            today=today_local().isoformat(),
            question=question,
            instruction=instruction,
            answer=answer,
        )

        raw = await generate_text(
            model=settings.gemini_extract_model,
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

        return OnboardingAnswerParser._parse_json(raw)

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
