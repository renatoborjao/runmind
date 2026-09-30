"""A IA (visão) LÊ o laudo da bioimpedância (foto/print) e devolve os números
estruturados. O atleta confere/edita antes de salvar — nunca grava no escuro."""

from __future__ import annotations

import json

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# campo → (mín, máx) plausíveis; fora disso vira None (leitura errada)
FIELDS: dict[str, tuple[float, float]] = {
    "weight_kg": (25, 250),
    "body_fat_pct": (2, 65),
    "fat_mass_kg": (1, 150),
    "lean_mass_kg": (15, 160),
    "muscle_mass_kg": (10, 120),
    "water_pct": (20, 80),
    "visceral_fat": (1, 30),
    "bmr_kcal": (700, 4500),
    "metabolic_age": (10, 90),
}

PROMPT = """Esta imagem é o laudo de uma BIOIMPEDÂNCIA (balança/aparelho de \
composição corporal) de um atleta. Extraia os valores exatamente como estão \
impressos. Se um campo não aparece, use null — NUNCA invente nem calcule.

Campos (números, ponto decimal):
- weight_kg: peso total em kg
- body_fat_pct: percentual de gordura corporal (%)
- fat_mass_kg: massa de gordura em kg
- lean_mass_kg: massa magra (livre de gordura) em kg
- muscle_mass_kg: massa muscular (esquelética) em kg
- water_pct: água corporal (%)
- visceral_fat: nível de gordura visceral (índice)
- bmr_kcal: taxa metabólica basal em kcal
- metabolic_age: idade metabólica em anos
- date: data da medição em AAAA-MM-DD se visível, senão null

Responda APENAS com JSON:
{"weight_kg": null, "body_fat_pct": null, "fat_mass_kg": null, \
"lean_mass_kg": null, "muscle_mass_kg": null, "water_pct": null, \
"visceral_fat": null, "bmr_kcal": null, "metabolic_age": null, "date": null}"""


def clean_reading(data: dict) -> dict:
    """Mantém só números plausíveis; o resto vira None."""

    out: dict = {}

    for key, (lo, hi) in FIELDS.items():

        try:

            v = float(data.get(key))

        except (TypeError, ValueError):

            v = None

        out[key] = round(v, 1) if v is not None and lo <= v <= hi else None

    date = data.get("date")

    out["date"] = date if isinstance(date, str) and len(date) == 10 else None

    return out


def _parse(raw: str) -> dict | None:

    try:

        data = json.loads(repair_json(raw))

    except (json.JSONDecodeError, TypeError, ValueError):

        return None

    if not isinstance(data, dict):

        return None

    return clean_reading(data)


class BodyCompositionReader:

    @staticmethod
    async def read(image_bytes: bytes, mimetype: str) -> dict | None:
        """Campos extraídos (todos opcionais) ou None se a IA não conseguiu."""

        try:

            result = await generate_json(
                model=get_settings().gemini_coach_model,
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes, mime_type=mimetype or "image/jpeg"
                    ),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=600,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
                parse=_parse,
            )

        except Exception as e:

            print(f"Falha ao ler bioimpedância: {e}")

            return None

        if result and any(result.get(k) is not None for k in FIELDS):

            return result

        return None
