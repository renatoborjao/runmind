"""Captura REATIVA do estado subjetivo: quando o atleta relata como se sente
("dormi mal", "tô detonado", "perna dolorida", "acordei inteiro"), extrai um
check-in estruturado (energia/sono/dor 1-5 + nota).

Portão barato por palavra-chave ANTES do Gemini (a maioria das mensagens não
fala de sensação) + extração estruturada espelhando o MemoryExtractionEngine
(generate_json, thinking_budget=0). Ver [[project_ideias_produto]] item 4."""

import json
import unicodedata

from google.genai import types

from app.core.config import get_settings
from app.domain.entities.daily_checkin import DailyCheckin
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 200

# portão: só chama o Gemini se a mensagem cheira a relato de sensação/sono/dor
_STATE_HINTS = (
    "dormi", "sono", "sonolen", "cansad", "cansaco", "exaust", "detonad",
    "zerad", "acabad", "moid", "inteir", "disposi", "disposicao", "energia",
    "energiz", "animad", "fadiga", "descansad", "descanso", "dor", "dolorid",
    "doendo", "doi ", "lesa", "lesio", "desconforto", "pesad", "leve hoje",
    "acordei", "me sinto", "to me sentindo", "tou me sentindo", "estou me sentindo",
)


class CheckinDetector:

    @staticmethod
    def mentions_state(text: str) -> bool:
        """True se a mensagem parece falar de sono/energia/dor — só então vale
        gastar uma chamada de extração."""

        normalized = CheckinDetector._normalize(text)

        return any(hint in normalized for hint in _STATE_HINTS)

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower()

        return "".join(
            c
            for c in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(c) != "Mn"
        )


_PROMPT = """Você lê a mensagem do corredor {runner_name} e extrai como ele \
está SE SENTINDO hoje (estado subjetivo do dia), se a mensagem disser algo a \
respeito.

MENSAGEM: {incoming_text}

Responda APENAS com JSON:
{{"energy": 1-5 ou null, "sleep_quality": 1-5 ou null, "soreness": 1-5 ou null, "note": "..."}}

ESCALAS (1-5):
- energy: 1=exausto/sem energia, 3=normal, 5=cheio de energia/disposto
- sleep_quality: 1=dormiu muito mal, 3=ok, 5=dormiu ótimo
- soreness: 1=nenhuma dor, 3=leve, 5=muita dor/desconforto (MAIOR = pior)
- note: só se houver detalhe útil (ex.: "dor na panturrilha direita"); senão ""

REGRAS:
- Preencha SÓ o que a mensagem indicar; o resto é null. Não invente.
- "dormi mal"→sleep_quality baixo; "tô detonado/zerado/acabado"→energy baixo; \
"perna/joelho doendo"→soreness alto + note; "acordei inteiro/disposto"→energy alto.
- Se a mensagem NÃO fala de sono/energia/dor/sensação, devolva tudo null e note "".
"""


class CheckinExtractor:

    @staticmethod
    async def extract(
        runner_name: str,
        incoming_text: str,
        day: str,
        at: str,
    ) -> DailyCheckin | None:
        """Devolve um DailyCheckin se a mensagem trouxe estado; None se não há
        nada de sensação (ou o JSON não veio)."""

        prompt = _PROMPT.format(
            runner_name=runner_name,
            incoming_text=incoming_text,
        )

        data = await generate_json(
            model=get_settings().gemini_extract_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            parse=CheckinExtractor._parse,
        )

        if not data:

            return None

        checkin = DailyCheckin(
            day=day,
            at=at,
            energy=data.get("energy"),
            sleep_quality=data.get("sleep_quality"),
            soreness=data.get("soreness"),
            note=data.get("note") or "",
        )

        return checkin if checkin.has_data else None

    @staticmethod
    def _parse(raw: str) -> dict | None:
        """None em JSON torto (pra o generate_json re-gerar); dict validado
        (só valores 1-5 ou None) quando o JSON é válido."""

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError):

            return None

        if not isinstance(data, dict):

            return None

        return {
            "energy": CheckinExtractor._scale(data.get("energy")),
            "sleep_quality": CheckinExtractor._scale(data.get("sleep_quality")),
            "soreness": CheckinExtractor._scale(data.get("soreness")),
            "note": data.get("note") if isinstance(data.get("note"), str) else "",
        }

    @staticmethod
    def _scale(value) -> int | None:
        """Aceita só inteiros 1-5; qualquer outra coisa vira None."""

        if isinstance(value, bool):

            return None

        if isinstance(value, (int, float)) and 1 <= value <= 5:

            return int(value)

        return None
