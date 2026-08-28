"""Fallback: quando o coach NÃO reconhece o modelo do tênis (categoria em
branco no registro), ele busca na web, lê os trechos reais e classifica —
função (prova/dia a dia) + vida útil típica. Free (DuckDuckGo, sem API key) e
best-effort: se a web falhar, devolve None e o par fica no padrão (sem quebrar
o registro). Ver [[project_tracker_tenis]] e [[feedback_free_tools_preference]]."""

import json
import re

import httpx
from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

_DDG_URL = "https://html.duckduckgo.com/html/"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_MAX_SNIPPET_CHARS = 2000

_MAX_TOKENS = 200

_CLASSIFY_PROMPT = """Trechos da web sobre o tênis de corrida "{name}":

{snippets}

Com base SÓ nesses trechos, classifique o tênis. Devolva UM JSON:
{{"category": "<prova|dia a dia>", "threshold_km": <vida útil típica em km, \
número>, "known": <true se os trechos falam MESMO deste tênis de corrida; false \
se forem genéricos/irrelevantes>}}

- "prova" = tênis de competição/placa de carbono/rápido/leve (vida útil ~350-500 \
km). "dia a dia" = trainer de treino/rodagem/amortecido (vida útil ~600-800 km).
- Se os trechos não deixarem claro que é um tênis de corrida específico, \
known=false."""


class ShoeWebLookup:

    @staticmethod
    async def classify(name: str) -> dict | None:
        """{category, threshold_km} do modelo, ou None se a web não ajudou.
        Best-effort ponta a ponta — qualquer falha vira None."""

        snippets = await ShoeWebLookup._search(name)

        if not snippets:

            return None

        info = await ShoeWebLookup._classify_from(name, snippets)

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
    async def _search(name: str) -> str:
        """Trechos de resultado do DuckDuckGo pro modelo. String vazia em
        qualquer falha (rede/bloqueio/HTML mudou)."""

        query = (
            f'"{name}" running shoe carbon plate racing or daily trainer '
            "how many miles lifespan"
        )

        try:

            async with httpx.AsyncClient(
                timeout=8, headers={"User-Agent": _UA}, follow_redirects=True
            ) as client:

                response = await client.get(_DDG_URL, params={"q": query})

            response.raise_for_status()

        except (httpx.HTTPError, httpx.InvalidURL):

            return ""

        return ShoeWebLookup._extract_snippets(response.text)

    @staticmethod
    def _extract_snippets(html: str) -> str:
        """Puxa o texto dos snippets de resultado; cai pro texto cru sem tags
        se o layout mudar. Limita o tamanho pra não inflar o prompt."""

        blocks = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL
        )

        text = " ".join(blocks) if blocks else html

        # tira tags e colapsa espaços
        text = re.sub(r"<[^>]+>", " ", text)

        text = re.sub(r"\s+", " ", text).strip()

        return text[:_MAX_SNIPPET_CHARS]

    @staticmethod
    async def _classify_from(name: str, snippets: str) -> dict | None:

        settings = get_settings()

        prompt = _CLASSIFY_PROMPT.format(name=name, snippets=snippets)

        return await generate_json(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=_MAX_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=ShoeWebLookup._parse,
        )

    @staticmethod
    def _parse(raw: str) -> dict | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        return data if isinstance(data, dict) else None
