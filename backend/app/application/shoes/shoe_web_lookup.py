"""Fallback: quando o coach NÃO reconhece o modelo do tênis (categoria em
branco no registro), ele PESQUISA na web pra classificar — função (prova/dia a
dia) + vida útil típica. Usa o GROUNDING de busca do próprio Gemini (google_search)
em vez de scraping: sem CAPTCHA/bloqueio de IP, confiável, dentro do tier free.
Best-effort: se a busca falhar/não achar, devolve None e o par fica no padrão
(sem quebrar o registro). Ver [[project_tracker_tenis]] e
[[feedback_free_tools_preference]]."""

import json

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_text,
    repair_json,
)

_MAX_TOKENS = 400

_PROMPT = """Pesquise na web o tênis de corrida "{name}" e classifique com base \
no que encontrar. Responda SÓ com um JSON (sem texto fora dele):
{{"category": "prova" ou "dia a dia", "threshold_km": <vida útil típica em km, \
número>, "known": true/false}}

- "prova" = tênis de competição / placa de carbono / rápido / leve (vida útil \
~350-500 km). "dia a dia" = trainer de treino/rodagem / amortecido (~600-800 km).
- known=false se você NÃO encontrar esse tênis de corrida específico na busca \
(não invente)."""


class ShoeWebLookup:

    @staticmethod
    async def classify(name: str) -> dict | None:
        """{category, threshold_km} do modelo pesquisado, ou None se a busca não
        ajudou. Best-effort ponta a ponta — qualquer falha vira None."""

        info = await ShoeWebLookup._search_and_classify(name)

        if not info or not info.get("known"):

            return None

        category = info.get("category")

        if category not in ("prova", "dia a dia"):

            category = None

        threshold = info.get("threshold_km")

        try:

            threshold = float(threshold) if threshold else None

        except (TypeError, ValueError):

            threshold = None

        if category is None and threshold is None:

            return None

        return {"category": category, "threshold_km": threshold}

    @staticmethod
    async def _search_and_classify(name: str) -> dict | None:
        """Uma chamada ao Gemini COM busca (google_search grounding): ele
        pesquisa o modelo e devolve o JSON. None em qualquer falha."""

        settings = get_settings()

        prompt = _PROMPT.format(name=name)

        try:

            raw = await generate_text(
                model=settings.gemini_chat_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    max_output_tokens=_MAX_TOKENS,
                ),
                require_text=True,
            )

        except Exception as e:

            print(f"Busca web de tênis (grounding) falhou p/ '{name}': {e}")

            return None

        return ShoeWebLookup._parse(raw)

    @staticmethod
    def _parse(raw: str) -> dict | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        return data if isinstance(data, dict) else None
