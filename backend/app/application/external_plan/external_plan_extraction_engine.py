import json

from google import genai
from google.genai import types

from app.core.config import get_settings

DEFAULT_MODEL = "gemini-2.5-flash"

MAX_OUTPUT_TOKENS = 1500

EXTRACTION_PROMPT = """Você lê planilhas de treino de corrida (print, foto \
ou PDF enviados por corredores brasileiros) e extrai as sessões da semana.

Responda APENAS com JSON neste formato:
{"sessions": [
  {"day": "Tuesday",
   "workout_type": "Intervalado",
   "objective": "6x800m forte",
   "distance_km": 8.0,
   "duration_minutes": null,
   "pace_min": "5:30",
   "pace_max": "6:00",
   "notes": "descanso 2min entre tiros"}
]}

REGRAS:
- "day": dia da semana em inglês capitalizado (Monday..Sunday). Se o
  plano usar datas, converta para o dia da semana.
- "workout_type": nome curto do treino como está no plano (Rodagem,
  Intervalado, Longão, Tempo Run, Regenerativo...).
- "distance_km": número em km; se o plano só der tempo, use
  "duration_minutes" e deixe distance_km null.
- "pace_min"/"pace_max": formato "M:SS" por km, se houver; senão null.
- "notes": detalhes relevantes (séries, descansos, observações).
- Ignore treinos que não sejam de corrida/caminhada (musculação, etc.).
- Se a imagem não contiver um plano de treino legível:
  {"sessions": []}
- NÃO invente sessões nem valores que não estejam no plano.
"""


class ExternalPlanExtractionEngine:

    @staticmethod
    async def extract(
        media_bytes: bytes,
        mimetype: str,
    ) -> list[dict]:

        settings = get_settings()

        client = genai.Client(
            api_key=settings.google_api_key,
        )

        response = await client.aio.models.generate_content(
            model=DEFAULT_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=media_bytes,
                    mime_type=mimetype,
                ),
                EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                # extração estruturada não precisa de raciocínio
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0,
                ),
            ),
        )

        return ExternalPlanExtractionEngine._parse_sessions(
            response.text or "",
        )

    @staticmethod
    def _parse_sessions(
        raw: str,
    ) -> list[dict]:

        try:

            data = json.loads(raw)

        except (json.JSONDecodeError, TypeError):

            return []

        if not isinstance(data, dict):

            return []

        sessions = data.get("sessions")

        if not isinstance(sessions, list):

            return []

        return [
            session
            for session in sessions
            if isinstance(session, dict)
        ]
