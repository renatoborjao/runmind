"""O coach VÊ a foto: a IA (visão) lê a imagem que o atleta mandou e devolve
o que ela mostra, em texto — que entra no MESMO pipeline de conversa (como o
áudio transcrito). Assim print de treino de outro app, resultado de prova,
foto do tênis ou do pé inchado viram contexto de verdade, e o coach responde
com o histórico completo do atleta (nunca no vácuo).

Também classifica se é um PLANO DE TREINO (planilha/print do treinador): pra
quem treina com treinador externo, isso vai pra leitura de plano.
"""

from __future__ import annotations

import json

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 700

KINDS = ("training_plan", "workout", "other")

PROMPT = """Um corredor mandou esta imagem pro treinador dele (app de \
corrida).{caption_block}

Descreva o que a imagem mostra de RELEVANTE pra um treinador de corrida, em
português do Brasil, em 1 a 4 frases objetivas. Transcreva números visíveis
(distância, tempo, pace, FC, splits, datas, posição, carga) com fidelidade.
NÃO dê conselho nem opinião — só descreva. Não invente o que não dá pra ver.

Classifique:
- "training_plan": planilha/print/PDF com os treinos PRESCRITOS de uma semana
  ou mais (plano de treinador).
- "workout": registro de um treino/prova já feito (print de relógio, Strava,
  esteira, resultado de prova, certificado).
- "other": qualquer outra coisa (corpo/lesão, tênis, comida, paisagem, exame…).

Responda APENAS com JSON:
{"kind": "training_plan" | "workout" | "other", "description": "..."}"""


def _parse(raw: str) -> dict | None:

    try:

        data = json.loads(repair_json(raw))

    except (json.JSONDecodeError, TypeError, ValueError):

        return None

    if not isinstance(data, dict):

        return None

    description = str(data.get("description") or "").strip()

    if not description:

        return None

    kind = data.get("kind")

    return {
        "kind": kind if kind in KINDS else "other",
        "description": description,
    }


class InboundImageReader:

    @staticmethod
    async def read(
        image_bytes: bytes,
        mimetype: str,
        caption: str = "",
    ) -> dict | None:
        """{"kind", "description"} ou None se a IA não conseguiu ler (quem
        chama avisa o atleta — foto nunca vira silêncio)."""

        caption = (caption or "").strip()

        caption_block = (
            f'\nO corredor escreveu junto: "{caption}"' if caption else ""
        )

        try:

            return await generate_json(
                model=get_settings().gemini_extract_model,
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mimetype or "image/jpeg",
                    ),
                    PROMPT.replace("{caption_block}", caption_block),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
                parse=_parse,
            )

        except Exception as e:

            print(f"Falha ao ler imagem do atleta: {e}")

            return None
