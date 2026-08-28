"""A inteligência do coach sobre TÊNIS vem da PESQUISA, não de lista fixa: ao
registrar, o coach pesquisa cada modelo na web (grounding de busca do Gemini,
`google_search`) e classifica — função (prova/dia a dia) + vida útil típica. Uma
busca cobre a lista inteira do atleta (rápido, um round-trip). Sem CAPTCHA/bloqueio
de IP, dentro do tier free. Best-effort: modelo não encontrado fica sem categoria
(o par não é chutado). Ver [[project_tracker_tenis]] e
[[feedback_free_tools_preference]]."""

import json

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_text,
    repair_json,
)

_MAX_TOKENS = 900

_PROMPT = """Pesquise na web CADA tênis de corrida da lista e classifique pelo \
que encontrar. Não invente: se não achar o modelo, category=null pra ele.

LISTA:
{shoes}

Responda APENAS com este JSON (nada antes/depois):
{{"shoes": [{{"name": "<o nome IGUAL ao da lista>", "category": "prova" ou "dia \
a dia" ou null, "threshold_km": <vida útil típica em km, número, ou null>}}, ...]}}

- "prova" = tênis que se usa pra VELOCIDADE/competição: racer, placa de carbono, \
speedster leve (vida útil ~350-500 km).
- "dia a dia" = tênis que se usa pra RODAGEM/volume: trainer de treino, super \
trainer versátil, max-cushion (vida útil ~600-800 km).
- Um mesmo modelo em cores diferentes é o MESMO tênis (classifique igual)."""


class ShoeWebLookup:

    @staticmethod
    async def classify_many(names: list[str]) -> dict[str, dict]:
        """Pesquisa e classifica VÁRIOS modelos numa busca só. Devolve
        {nome_minúsculo: {category, threshold_km}} só pros que a web reconheceu
        (com função OU vida útil). {} em qualquer falha."""

        names = [n for n in names if n and n.strip()]

        if not names:

            return {}

        raw = await ShoeWebLookup._search(names)

        if raw is None:

            return {}

        entries = ShoeWebLookup._parse_many(raw)

        result: dict[str, dict] = {}

        for entry in entries:

            name = str(entry.get("name") or "").strip().lower()

            if not name:

                continue

            info = ShoeWebLookup._clean(entry)

            if info is not None:

                result[name] = info

        return result

    @staticmethod
    def _clean(entry: dict) -> dict | None:

        category = ShoeWebLookup._normalize_category(entry.get("category"))

        threshold = entry.get("threshold_km")

        try:

            threshold = float(threshold) if threshold else None

        except (TypeError, ValueError):

            threshold = None

        if category is None and threshold is None:

            return None

        return {"category": category, "threshold_km": threshold}

    @staticmethod
    async def _search(names: list[str]) -> str | None:

        settings = get_settings()

        listing = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(names))

        prompt = _PROMPT.format(shoes=listing)

        try:

            return await generate_text(
                model=settings.gemini_chat_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    max_output_tokens=_MAX_TOKENS,
                ),
                require_text=True,
            )

        except Exception as e:

            print(f"Pesquisa web de tênis (grounding) falhou: {e}")

            return None

    @staticmethod
    def _normalize_category(value) -> str | None:
        """Mapeia o rótulo que a IA trouxer pros dois baldes (por USO). A ordem
        checa os sinais de PROVA (velocidade/placa) antes dos de rodagem."""

        text = (value or "").lower()

        if text in ("prova", "dia a dia"):

            return text

        prova_cues = (
            "prova", "race", "raci", "carbon", "placa", "speed", "plated",
            "competi", "fast", "leve",
        )

        daily_cues = (
            "dia a dia", "daily", "trainer", "rodagem", "amortec", "cushion",
            "easy", "treino", "super trainer",
        )

        if any(cue in text for cue in prova_cues):

            return "prova"

        if any(cue in text for cue in daily_cues):

            return "dia a dia"

        return None

    @staticmethod
    def _parse_many(raw: str) -> list[dict]:

        data = ShoeWebLookup._parse(raw)

        if not isinstance(data, dict):

            return []

        shoes = data.get("shoes")

        return shoes if isinstance(shoes, list) else []

    @staticmethod
    def _parse(raw: str) -> dict | None:

        try:

            return json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return ShoeWebLookup._extract_json_object(raw)

    @staticmethod
    def _extract_json_object(raw: str) -> dict | None:
        """Acha o primeiro objeto {...} no texto (grounding às vezes emenda
        citações/prosa antes do JSON)."""

        if not raw:

            return None

        start = raw.find("{")

        end = raw.rfind("}")

        if start == -1 or end <= start:

            return None

        try:

            data = json.loads(repair_json(raw[start:end + 1]))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        return data if isinstance(data, dict) else None
