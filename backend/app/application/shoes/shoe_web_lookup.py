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

# grounding consome tokens na busca; folga pra o JSON sair inteiro
_MAX_TOKENS = 800

_PROMPT = """Pesquise na web o tênis de corrida "{name}" e classifique. Responda \
APENAS com o JSON abaixo, nada antes nem depois:
{{"category": "prova" OU "dia a dia", "threshold_km": <vida útil típica em km, só \
o número>, "known": true/false}}

- category tem que ser EXATAMENTE "prova" ou "dia a dia" (não invente outros \
rótulos): tênis rápido/leve/com placa (racer OU "super trainer" com placa) = \
"prova" (vida útil ~350-500 km); trainer amortecido de rodagem/dia a dia = "dia \
a dia" (~600-800 km).
- known=false se você NÃO encontrar esse tênis de corrida específico (não \
invente)."""


class ShoeWebLookup:

    @staticmethod
    async def classify(name: str) -> dict | None:
        """{category, threshold_km} do modelo pesquisado, ou None se a busca não
        ajudou. Best-effort ponta a ponta — qualquer falha vira None."""

        info = await ShoeWebLookup._search_and_classify(name)

        if not info or not info.get("known"):

            return None

        category = ShoeWebLookup._normalize_category(info.get("category"))

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
    def _normalize_category(value) -> str | None:
        """Mapeia o rótulo que a IA trouxer pros dois baldes. O grounding às
        vezes inventa termo ('super trainer', 'racing') — a ordem checa os
        sinais de PROVA (placa/rápido) antes dos de rodagem."""

        text = (value or "").lower()

        if text in ("prova", "dia a dia"):

            return text

        prova_cues = (
            "prova", "race", "raci", "carbon", "placa", "speed", "plated",
            "super trainer", "competi", "tempo", "fast", "leve",
        )

        daily_cues = (
            "dia a dia", "daily", "trainer", "rodagem", "amortec", "cushion",
            "easy", "treino",
        )

        if any(cue in text for cue in prova_cues):

            return "prova"

        if any(cue in text for cue in daily_cues):

            return "dia a dia"

        return None

    @staticmethod
    def _parse(raw: str) -> dict | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            data = ShoeWebLookup._extract_json_object(raw)

        return data if isinstance(data, dict) else None

    @staticmethod
    def _extract_json_object(raw: str) -> dict | None:
        """Fallback: acha o primeiro objeto {...} no texto (grounding às vezes
        emenda citações/prosa antes do JSON)."""

        if not raw:

            return None

        start = raw.find("{")

        end = raw.rfind("}")

        if start == -1 or end <= start:

            return None

        try:

            return json.loads(repair_json(raw[start:end + 1]))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None
