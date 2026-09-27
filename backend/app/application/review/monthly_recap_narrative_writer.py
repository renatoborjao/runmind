"""Escreve a frase de fechamento do recap mensal via IA — tom de
COMEMORAÇÃO (o resumo semanal já cobre a leitura tática; aqui é o balanço do
mês, pensado pra soar bem mesmo se o atleta encaminhar pra um amigo). Se a IA
falhar/vier vazia, retorna None e o formatter usa o fallback determinístico —
a mensagem nunca vira silêncio."""

import json

from google.genai import types

from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 800

THINKING_BUDGET = 256

MAX_SENTENCES = 2

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente fechando o \
MÊS do atleta por mensagem (WhatsApp) — um balanço caloroso, tipo "olha só o \
que você fez esse mês". A mensagem pode ser ENCAMINHADA pelo atleta pros \
amigos, então o tom é de celebração, não de análise técnica.

FATOS DO MÊS (use SÓ isto, não invente número):
{facts}

REGRAS:
- Tom de comemoração e orgulho genuíno — reconheça o esforço do mês inteiro.
- Se houver recorde(s) batido(s), destaque com entusiasmo. Sem recorde, \
celebre o que foi REAL (o volume, a constância, o que ele de fato fez) — sem \
inflar: mês fraco não vira "mês incrível"; aí reconheça o que ele fez e \
aponte, em meia frase, o que o próximo mês pede. Elogio vazio perde o valor \
do elogio verdadeiro.
- Nunca invente número que não esteja nos fatos.
- Português do Brasil, direto, humano. Sem emojis, sem títulos, sem markdown.
- {max_sentences} frases curtas no MÁXIMO.

Responda APENAS com JSON:
{{"reading": ["frase 1", "frase 2"]}}
"""


class MonthlyRecapNarrativeWriter:

    @staticmethod
    async def write(
        runner_name: str,
        recap: dict,
        profile: str | None = None,
    ) -> list[str] | None:

        try:

            facts = MonthlyRecapNarrativeWriter._facts(runner_name, recap, profile)

            settings = get_settings()

            return await generate_json(
                model=settings.gemini_coach_model,
                contents=PROMPT_TEMPLATE.format(
                    facts=facts,
                    max_sentences=MAX_SENTENCES,
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET,
                    ),
                ),
                parse=MonthlyRecapNarrativeWriter._parse,
            )

        except Exception as e:

            print(f"IA falhou no recap mensal, fallback: {e}")

            return None

    @staticmethod
    def _parse(raw: str) -> list[str] | None:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        sentences = data.get("reading") if isinstance(data, dict) else None

        if not isinstance(sentences, list):

            return None

        lines = [str(s).strip() for s in sentences if str(s).strip()]

        return lines or None

    @staticmethod
    def _facts(runner_name: str, recap: dict, profile: str | None = None) -> str:

        lines = [
            f"Atleta: {runner_name}",
            f"Mês: {recap['month_label']}",
            f"Total: {recap['total_km']:.1f} km em {recap['total_runs']} "
            "treino(s)",
            f"Maior treino do mês: {recap['longest_km']:.1f} km",
            f"Consistência do mês: {recap['consistency']:.0f}%",
        ]

        records = recap.get("records") or []

        if records:

            lines.append("Recordes batidos neste mês: " + "; ".join(records))

        else:

            lines.append("Nenhum recorde novo neste mês.")

        predicted = recap.get("predicted_time")

        if predicted:

            lines.append(
                f"Previsão de prova no ritmo atual: {predicted['formatted']}."
            )

        # o DOSSIÊ: o mês lido à luz de quem ele é e do que o coach vem
        # decidindo — mesma base de todas as vozes
        if profile:

            from app.application.coach.context.athlete_dossier import (
                AthleteDossier,
            )

            dossier = AthleteDossier.render(profile)

            if dossier:

                lines.append(dossier)

        return "\n".join(lines)
