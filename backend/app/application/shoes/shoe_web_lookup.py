"""A inteligência do coach sobre TÊNIS vem da PESQUISA, não de lista fixa: ao
registrar, o coach pesquisa cada modelo na web (grounding de busca do Gemini,
`google_search`) e classifica — função (prova/dia a dia) + vida útil típica.
Pesquisa CADA par numa chamada própria (confiável), mas TODAS em paralelo
(asyncio.gather) — rápido mesmo pra vários pares. Sem CAPTCHA/bloqueio de IP,
dentro do tier free. Best-effort: modelo não encontrado fica sem categoria (o
par não é chutado). Ver [[project_tracker_tenis]] e
[[feedback_free_tools_preference]]."""

import asyncio
import json

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_text,
    repair_json,
)

# grounding consome tokens na busca; folga pra o JSON de UM tênis sair inteiro
_MAX_TOKENS = 800

_PROMPT = """Pesquise na web o tênis de corrida "{name}" e classifique. Responda \
APENAS com o JSON abaixo, nada antes nem depois:
{{"category": "rápido" OU "versátil" OU "dia a dia", "threshold_km": <vida útil \
típica em km, só o número>, "known": true/false}}

A pergunta-chave é o USO: dá pra fazer TREINO RÁPIDO (tempo/tiro) nele, ou é de \
CONFORTO pra rodagem?
- "rápido" = racer / placa de carbono / competição pura (vida útil ~350-500 km).
- "versátil" = super trainer LEVE e RESPONSIVO que serve pra TEMPO/treino rápido \
também (ex.: Superblast, Endorphin Speed, Deviate Nitro) — vida útil ~500-650 km.
- "dia a dia" = trainer de CONFORTO/amortecimento pra rodagem/longão. INCLUI \
super trainer MAX-CUSHION pesado que NÃO é pra velocidade (ex.: Neo Vista, Bondi, \
Skyward): se você NÃO faria tiro/tempo nele, é "dia a dia" (~600-800 km).
- known=false se você NÃO encontrar esse tênis de corrida específico (não \
invente)."""


class ShoeWebLookup:

    @staticmethod
    async def classify_many(names: list[str]) -> dict[str, dict]:
        """Pesquisa e classifica VÁRIOS modelos, cada um na sua chamada mas
        TODAS em paralelo. Devolve {nome_minúsculo: {category, threshold_km}} só
        pros que a web reconheceu. {} se a lista vier vazia."""

        names = [n for n in names if n and n.strip()]

        if not names:

            return {}

        results = await asyncio.gather(
            *(ShoeWebLookup.classify(n) for n in names)
        )

        return {
            name.strip().lower(): info
            for name, info in zip(names, results)
            if info is not None
        }

    @staticmethod
    async def classify(name: str) -> dict | None:
        """{category, threshold_km} de UM modelo pesquisado, ou None se a web
        não ajudou. Best-effort ponta a ponta — qualquer falha vira None."""

        info = await ShoeWebLookup._search(name)

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
    async def _search(name: str) -> dict | None:
        """Uma chamada ao Gemini COM busca (google_search): pesquisa o modelo e
        devolve o JSON parseado. None em qualquer falha."""

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

            print(f"Pesquisa web de tênis (grounding) falhou p/ '{name}': {e}")

            return None

        return ShoeWebLookup._parse(raw)

    @staticmethod
    def _normalize_category(value) -> str | None:
        """Mapeia o rótulo que a IA trouxer pros 3 níveis. A ordem checa VERSÁTIL
        (super trainer) e RÁPIDO (racer/placa) antes de cair em dia a dia."""

        text = (value or "").lower()

        if text in ("rápido", "rapido", "prova", "versátil", "versatil",
                    "dia a dia"):

            if text in ("rápido", "rapido", "prova"):

                return "rápido"

            return "versátil" if text in ("versátil", "versatil") else text

        versatil_cues = (
            "versát", "versat", "super trainer", "supertrainer", "super-trainer",
            "tempo", "speed trainer",
        )

        rapido_cues = (
            "rápido", "rapido", "veloz", "prova", "race", "raci", "carbon",
            "placa", "plated", "competi", "racer",
        )

        daily_cues = (
            "dia a dia", "daily", "trainer", "rodagem", "amortec", "cushion",
            "easy", "treino", "max",
        )

        if any(cue in text for cue in versatil_cues):

            return "versátil"

        if any(cue in text for cue in rapido_cues):

            return "rápido"

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
