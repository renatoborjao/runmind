"""DOSSIÊ DA PROVA — o coach sabe da prova do mundo real, não só da distância.

Uma pesquisa na web (Gemini + busca do Google) por PROVA, guardada e
COMPARTILHADA entre atletas (dez atletas na mesma maratona = uma busca): percurso,
altimetria e subidas, largada, piso, hidratação, clima típico e dicas de
estratégia ancoradas no percurso — com as fontes. Perto da data, atualiza a
previsão do tempo.

Custo sob controle: pesquisa só em JOB diário / cadastro da prova — NUNCA no
caminho da conversa (a conversa só LÊ o cache). Prova com nome genérico ("10 km")
não é pesquisada (não dá pra saber qual é).

Consumo: contexto da conversa, plano, estratégia de prova e acompanhante de
prova (semana/véspera/dia). Ver [[project_race_intel]].
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime

from google.genai import types

from app.core.clock import now_local, today_local
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_text,
    repair_json,
)
from app.infrastructure.persistence.race_intel_repository import (
    RaceIntelRepository,
)

# dossiê do percurso vale bastante (percurso muda pouco); re-pesquisa se velho
RESEARCH_MAX_AGE_DAYS = 90

# só vale pesquisar provas até ~6 meses à frente (antes disso muda muito)
RESEARCH_HORIZON_DAYS = 200

# previsão do tempo: só faz sentido na última semana; no máx. 1x por dia
FORECAST_WINDOW_DAYS = 7

MAX_TIPS = 3

MAX_HILLS = 4

# palavras que NÃO identificam uma prova (sobrando só isso, o nome é genérico)
_GENERIC_WORDS = {
    "km", "k", "prova", "corrida", "meia", "maratona", "de", "da", "do", "rua",
    "run", "race", "half", "marathon", "trail", "mi", "milhas", "treino",
}

RESEARCH_PROMPT = """Você é o assistente de pesquisa de um treinador de corrida. \
Pesquise na web a prova abaixo e reúna o que importa pra um corredor se preparar.

Prova: "{name}"
Data informada pelo atleta: {date}
País: Brasil (salvo se o nome indicar outro)

Responda APENAS com JSON (sem texto fora dele), neste formato:
{{
  "identified": true,
  "official_name": "nome oficial",
  "city": "cidade/UF",
  "date_confirmed": true,
  "start_time": "07:00" ou null,
  "distance_km": 15,
  "course": "percurso em 1-2 frases (por onde passa, formato: ida-e-volta, voltas...)",
  "elevation": "plano" | "ondulado" | "com subidas fortes",
  "elevation_gain_m": 120 ou null,
  "hills": ["km 8-10: subida longa na Av. X"],
  "surface": "asfalto" | "terra" | "misto" | null,
  "hydration": "postos a cada ~3 km" ou null,
  "typical_weather": "clima típico na data/horário (temperatura, umidade)",
  "strategy_tips": ["dica curta e prática ancorada no percurso"]
}}

REGRAS:
- Só afirme o que as fontes mostram. O que não achar: null (ou lista vazia).
- Se não der pra identificar COM SEGURANÇA qual é a prova (nome ambíguo, várias
  provas iguais, nada encontrado): {{"identified": false}}.
- "date_confirmed": true só se a data da fonte bater com a informada.
- "hills": no máximo 4, com o km aproximado. "strategy_tips": no máximo 3,
  específicas desse percurso (ex.: "segure o ritmo na subida do km 9 e
  recupere na descida"), nada genérico.
- Português do Brasil."""

FORECAST_PROMPT = """Pesquise a PREVISÃO DO TEMPO para {city} em {date} no \
horário da manhã (largada {start}). Responda APENAS com JSON:
{{"forecast": "resumo curto: temperatura na largada e ao longo da manhã, chuva, \
umidade, vento — ou null se não houver previsão publicada ainda"}}"""


def race_key(name: str, race_date: str) -> str:
    """Chave do cache COMPARTILHADO: nome normalizado + data."""

    norm = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()

    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")[:80]

    return f"{slug}_{race_date}"


def is_specific(name: str) -> bool:
    """True se o nome identifica uma prova ("Maratona do Rio", "Santander Track&
    Field Villa-Lobos"); False pra genéricos ("10 km", "Meia maratona")."""

    norm = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()

    words = [w for w in re.findall(r"[a-z]+", norm.lower()) if w not in _GENERIC_WORDS]

    return sum(len(w) for w in words) >= 3


def _parse_json(raw: str) -> dict | None:

    try:

        data = json.loads(repair_json(raw))

    except (json.JSONDecodeError, TypeError, ValueError):

        return None

    return data if isinstance(data, dict) else None


def _sources(response) -> list[dict]:
    """Fontes (título + link) da busca no Google, pra dar crédito e rastrear."""

    out: list[dict] = []

    try:

        meta = response.candidates[0].grounding_metadata

        for chunk in (meta.grounding_chunks or []):

            web = getattr(chunk, "web", None)

            if web and getattr(web, "uri", None):

                out.append({"title": web.title or "", "url": web.uri})

    except Exception:

        pass

    return out[:6]


def _clean(data: dict) -> dict:
    """Normaliza o que a IA devolveu (limites, tipos) — nunca confia cego."""

    def _s(v):
        return str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else None

    def _list(v, n):
        return [str(x).strip() for x in (v or []) if isinstance(x, str) and x.strip()][:n]

    gain = data.get("elevation_gain_m")

    return {
        "identified": True,
        "official_name": _s(data.get("official_name")),
        "city": _s(data.get("city")),
        "date_confirmed": bool(data.get("date_confirmed")),
        "start_time": _s(data.get("start_time")),
        "distance_km": data.get("distance_km") if isinstance(data.get("distance_km"), (int, float)) else None,
        "course": _s(data.get("course")),
        "elevation": _s(data.get("elevation")),
        "elevation_gain_m": int(gain) if isinstance(gain, (int, float)) and 0 <= gain < 5000 else None,
        "hills": _list(data.get("hills"), MAX_HILLS),
        "surface": _s(data.get("surface")),
        "hydration": _s(data.get("hydration")),
        "typical_weather": _s(data.get("typical_weather")),
        "strategy_tips": _list(data.get("strategy_tips"), MAX_TIPS),
    }


async def _grounded(prompt: str) -> tuple[dict | None, list[dict]]:
    """Uma chamada ao Gemini COM busca no Google. (json, fontes)."""

    capture: list = []

    raw = await generate_text(
        model=get_settings().gemini_chat_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=1500,
        ),
        capture=capture,
    )

    return _parse_json(raw), (_sources(capture[-1]) if capture else [])


class RaceIntelService:

    # ---------------------------------------------------------- pesquisa

    @staticmethod
    async def research(name: str, race_date: str) -> dict:
        """Pesquisa a prova na web e devolve o dossiê (identified False se não
        deu pra saber qual é). Não grava."""

        data, sources = await _grounded(
            RESEARCH_PROMPT.format(name=name, date=race_date),
        )

        if not data or not data.get("identified"):

            return {"identified": False}

        intel = _clean(data)

        intel["sources"] = sources

        return intel

    @staticmethod
    async def ensure(name: str, race_date: str, today: date | None = None) -> dict | None:
        """Garante o dossiê da prova no cache (pesquisa se falta/velho) e a
        previsão do tempo na última semana. Devolve o dossiê (ou None se a prova
        não é pesquisável). Falha nunca propaga (é job de fundo)."""

        today = today or today_local()

        try:

            d = date.fromisoformat(race_date)

        except (TypeError, ValueError):

            return None

        days = (d - today).days

        if days < 0 or days > RESEARCH_HORIZON_DAYS or not is_specific(name):

            return None

        repo = RaceIntelRepository()

        key = race_key(name, race_date)

        intel = repo.load(key)

        try:

            if intel is None or RaceIntelService._stale(intel, today):

                intel = await RaceIntelService.research(name, race_date)

                intel.update({
                    "query_name": name,
                    "race_date": race_date,
                    "researched_at": now_local().isoformat(),
                })

                repo.save(key, intel)

                print(f"[race_intel] pesquisada '{name}' ({race_date}): "
                      f"identified={intel.get('identified')}")

            if intel.get("identified") and 0 <= days <= FORECAST_WINDOW_DAYS:

                intel = await RaceIntelService._refresh_forecast(key, intel, race_date, today)

        except Exception as e:

            print(f"[race_intel] falha ao pesquisar '{name}': {e}")

        return intel

    @staticmethod
    def _stale(intel: dict, today: date) -> bool:

        try:

            at = datetime.fromisoformat(intel["researched_at"]).date()

        except (KeyError, TypeError, ValueError):

            return True

        return (today - at).days > RESEARCH_MAX_AGE_DAYS

    @staticmethod
    async def _refresh_forecast(key: str, intel: dict, race_date: str, today: date) -> dict:

        prev = intel.get("forecast") or {}

        if prev.get("date") == today.isoformat():

            return intel  # já atualizou hoje

        data, _ = await _grounded(
            FORECAST_PROMPT.format(
                city=intel.get("city") or intel.get("official_name") or "",
                date=race_date,
                start=intel.get("start_time") or "manhã",
            ),
        )

        text = (data or {}).get("forecast")

        if isinstance(text, str) and text.strip():

            intel["forecast"] = {"text": text.strip(), "date": today.isoformat()}

            RaceIntelRepository().save(key, intel)

        return intel

    # ---------------------------------------------------------- leitura

    @staticmethod
    def cached(name: str | None, race_date) -> dict | None:
        """Dossiê JÁ pesquisado (só leitura, nunca pesquisa). None se não há."""

        if not name or not race_date:

            return None

        iso = race_date.isoformat() if hasattr(race_date, "isoformat") else str(race_date)

        intel = RaceIntelRepository().load(race_key(name, iso))

        return intel if intel and intel.get("identified") else None

    @staticmethod
    def for_runner(runner) -> dict | None:
        """Dossiê da prova-âncora do atleta (target_race/race_date), do cache."""

        return RaceIntelService.cached(
            getattr(runner, "target_race", None), getattr(runner, "race_date", None),
        )

    # ---------------------------------------------------------- textos

    @staticmethod
    def render_context(intel: dict | None) -> str:
        """Bloco pro prompt do coach (conversa/plano): fatos da prova real."""

        if not intel:

            return ""

        lines = [f"Dossiê da prova (pesquisado na web): {intel.get('official_name') or intel.get('query_name')}"]

        facts = [
            ("Local", intel.get("city")),
            ("Largada", intel.get("start_time")),
            ("Percurso", intel.get("course")),
            ("Altimetria", " — ".join(x for x in (
                intel.get("elevation"),
                f"~{intel['elevation_gain_m']} m de ganho" if intel.get("elevation_gain_m") else None,
            ) if x) or None),
            ("Piso", intel.get("surface")),
            ("Hidratação", intel.get("hydration")),
            ("Clima típico", intel.get("typical_weather")),
        ]

        lines += [f"- {k}: {v}" for k, v in facts if v]

        if intel.get("hills"):

            lines.append("- Trechos de subida: " + "; ".join(intel["hills"]))

        forecast = (intel.get("forecast") or {}).get("text")

        if forecast:

            lines.append(f"- Previsão do tempo pro dia: {forecast}")

        if intel.get("strategy_tips"):

            lines.append("- Dicas do percurso: " + " | ".join(intel["strategy_tips"]))

        if not intel.get("date_confirmed"):

            lines.append("- (a data da fonte não bateu 100% com a informada — confirme com o atleta se o assunto surgir)")

        lines.append("Use esses fatos quando fizer sentido (estratégia, treino de subida, calor); não invente além disso.")

        return "\n".join(lines)

    @staticmethod
    def briefing(intel: dict | None, with_tips: bool = True) -> str:
        """Linhas curtas pro ATLETA (estratégia de prova / semana / véspera)."""

        if not intel:

            return ""

        parts = []

        course = intel.get("elevation")

        if intel.get("hills"):

            course = f"{course or 'tem subidas'} — atenção: {intel['hills'][0]}"

        if course:

            parts.append(f"📍 Percurso: {course}")

        forecast = (intel.get("forecast") or {}).get("text")

        if forecast:

            parts.append(f"🌡️ Previsão: {forecast}")

        elif intel.get("start_time"):

            parts.append(f"⏰ Largada às {intel['start_time']}")

        if with_tips and intel.get("strategy_tips"):

            parts.append("💡 " + intel["strategy_tips"][0])

        return "\n".join(parts)

    # ---------------------------------------------------------- job diário

    @staticmethod
    async def refresh_all(today: date | None = None) -> None:
        """Job diário: garante o dossiê de TODA prova futura de atleta ativo
        (lista do app + âncora do perfil) e a previsão na última semana. Uma
        busca por prova, mesmo que vários atletas corram a mesma."""

        from app.infrastructure.persistence.race_repository import RaceRepository
        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        profiles = RunnerProfileRepository()

        seen: set[str] = set()

        for profile in profiles.list_active():

            try:

                runner = profiles.load(profile)

                races = [
                    (r["name"], r["date"])
                    for r in RaceRepository().load(profile)
                    if r.get("name") and r.get("date")
                ]

                if runner.target_race and runner.race_date:

                    rd = runner.race_date

                    races.append((runner.target_race, rd.isoformat() if hasattr(rd, "isoformat") else str(rd)))

            except Exception as e:

                print(f"[race_intel] falha ao ler provas de '{profile}': {e}")

                continue

            for name, race_date in races:

                key = race_key(name, race_date)

                if key in seen:

                    continue

                seen.add(key)

                await RaceIntelService.ensure(name, race_date, today)
