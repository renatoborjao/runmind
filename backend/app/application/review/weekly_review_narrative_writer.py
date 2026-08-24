"""Escreve a 'leitura da semana' do resumo de domingo via IA — voz de
treinador, ancorada nos números determinísticos E no OBJETIVO do atleta: quem
mira uma prova/marca ouve sobre o progresso rumo a ela; quem quer saúde/bem-
estar ouve sobre constância e evolução sustentável, sem cobrança de pace de
prova. Se a IA falhar/vier vazia, retorna None e o formatter usa o fallback
determinístico — a mensagem nunca vira silêncio."""

import json

from google.genai import types

from app.application.planner.pace_formatter import PaceFormatter
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

MAX_OUTPUT_TOKENS = 1200

THINKING_BUDGET = 256

MAX_SENTENCES = 3

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente fechando a \
SEMANA do atleta por mensagem (WhatsApp). Escreva a "leitura da semana": um \
resumo curto, humano e ESPECÍFICO do desempenho e da evolução — como um \
treinador que acompanha ELE.

FATOS DA SEMANA (use SÓ isto, não invente número):
{facts}

REGRAS:
- Se houver "DESTAQUE DA SEMANA — PROVA", ela é O ponto alto: ABRA celebrando \
a prova e o resultado (é o dia mais importante). E NÃO atribua o pace médio da \
semana a evolução de treino — a prova (esforço máximo) o puxou.
- FALE A LÍNGUA DO OBJETIVO do atleta (está nos fatos). Se ele mira uma PROVA \
ou MARCA de tempo, enquadre o progresso rumo a ela: o que evoluiu, quantas \
semanas faltam, o que ainda precisa apertar. Se o objetivo é SAÚDE/bem-estar/\
constância/emagrecer (SEM prova), foque em regularidade, hábito, sensação e \
evolução sustentável — NÃO cobre pace de prova nem meta de tempo. Se houver \
MAIS DE UM objetivo, contemple todos com equilíbrio.
- Comente o que ESTES números mostram (volume, pace, tendência, consistência, \
aderência ao plano) — nada de frase genérica que serviria pra qualquer semana.
- Se houver "QUEM É O ATLETA NO LONGO PRAZO", personalize com isso — conecte a \
semana à trajetória/evolução dele e respeite o que ele já contou (memória) e o \
que você aprendeu que funciona pra ele. Nunca contrarie esses fatos.
- Seja honesto: reconheça o que foi bem E aponte com leveza o que dá pra \
melhorar, sempre construtivo. Sem bronca.
- Tom de treinador de verdade: direto, humano, encorajador. Fale com "você". \
Português do Brasil. Sem emojis, sem títulos, sem markdown.
- {max_sentences} frases curtas no MÁXIMO, cada uma um ponto.

Responda APENAS com JSON:
{{"reading": ["frase 1", "frase 2"]}}
"""


class WeeklyReviewNarrativeWriter:

    @staticmethod
    async def write(
        runner_name: str,
        review: dict,
        profile: str | None = None,
    ) -> list[str] | None:

        try:

            facts = WeeklyReviewNarrativeWriter._facts(
                runner_name, review, profile,
            )

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
                parse=WeeklyReviewNarrativeWriter._parse,
            )

        except Exception as e:

            print(f"IA falhou no resumo semanal, fallback: {e}")

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
    def _facts(runner_name: str, review: dict, profile: str | None = None) -> str:

        comparison = review["comparison"]

        current = comparison["current_week"]

        previous = comparison["previous_week"]

        delta = comparison["delta"]

        goal = review.get("goal") or {}

        lines = [f"Atleta: {runner_name}"]

        # a PROVA da semana é o DESTAQUE — vem primeiro pra a IA não ignorar o
        # dia mais importante (era a queixa do Renato)
        race_fact = WeeklyReviewNarrativeWriter._race_fact(review.get("race"))

        if race_fact:

            lines.append(race_fact)

        lines.append(WeeklyReviewNarrativeWriter._goal_fact(goal))

        vol_delta = (
            f" ({delta['volume_delta_percent']:+.1f}%)"
            if delta.get("volume_delta_percent") is not None
            else ""
        )

        lines.append(
            f"Volume: {current['distance_km']:.1f} km "
            f"(anterior {previous['distance_km']:.1f} km{vol_delta})"
        )

        lines.append(
            f"Treinos: {current['runs']} (anterior {previous['runs']})"
        )

        lines.append(
            "Pace médio: "
            f"{WeeklyReviewNarrativeWriter._pace(current['avg_pace_min_km'])} "
            f"(anterior "
            f"{WeeklyReviewNarrativeWriter._pace(previous['avg_pace_min_km'])})"
        )

        trends = review.get("trends") or {}

        lines.append(WeeklyReviewNarrativeWriter._trend_fact(trends))

        adherence = review.get("adherence")

        if adherence:

            lines.append(
                f"Aderência ao plano: {adherence['done']} de "
                f"{adherence['planned']} treinos"
            )

        if review.get("longest_km"):

            lines.append(f"Maior treino da semana: {review['longest_km']:.1f} km")

        lines.append(f"Consistência recente: {review.get('consistency', 0):.0f}%")

        # quem é o atleta no longo prazo (memória + aprendizados + evolução) —
        # a leitura da semana fala com quem ELE é, não genérico. LEI
        # [[feedback_base_historico_sempre]]. Best-effort (vazio se sem lastro).
        if profile:

            from app.application.coach.context.athlete_brief import (
                AthleteLongTermBrief,
            )

            brief = AthleteLongTermBrief.render(profile)

            if brief:

                lines.append(brief)

        return "\n".join(line for line in lines if line)

    @staticmethod
    def _race_fact(race: dict | None) -> str:
        """A prova da semana como DESTAQUE + a ressalva de que ela puxa o pace
        médio (pra a IA não ler o médio como evolução de treino)."""

        if not race:

            return ""

        label = race.get("race_label") or "prova"

        time = race.get("time")

        target = race.get("target_time")

        beat = race.get("beat")

        if beat is True:

            outcome = f"BATEU a meta de {target}"

        elif beat is False:

            outcome = f"ficou acima da meta de {target}"

        else:

            outcome = "concluída"

        return (
            f"DESTAQUE DA SEMANA — PROVA: {label} em {time} ({outcome}). "
            "CELEBRE isto como o ponto alto da semana. ATENÇÃO: o pace médio da "
            "semana está PUXADO por esta prova (esforço máximo), NÃO é pace de "
            "treino — não trate o pace médio como evolução de forma; a evolução "
            "real está na tendência/EF."
        )

    @staticmethod
    def _goal_fact(goal: dict) -> str:

        name = goal.get("name") or "não definido"

        if goal.get("has_race"):

            weeks = goal.get("weeks_to_race")

            race_label = goal.get("race_label") or "prova"

            target = (
                f", alvo {goal['target_time']}" if goal.get("target_time") else ""
            )

            faltam = f", faltam {weeks} semanas" if weeks is not None else ""

            predicted = goal.get("predicted_time")

            previsao = (
                f" Previsão no ritmo atual: {predicted['formatted']}."
                if predicted
                else ""
            )

            # separa a PROVA (distância + contagem) do OBJETIVO de fundo (name):
            # a prova de 10k não é "a meta de 21km em 2 semanas".
            return (
                f"Próxima prova: {race_label}{target}{faltam}. "
                f"Objetivo de fundo: {name}.{previsao}"
            )

        return (
            f"Objetivo (SEM prova — saúde/evolução): {name}. "
            "NÃO cobre pace de prova nem meta de tempo."
        )

    @staticmethod
    def _trend_fact(trends: dict) -> str:

        parts = []

        volume = trends.get("volume") or {}

        if volume.get("delta_percent") is not None:

            parts.append(f"volume {volume['delta_percent']:+.1f}%")

        pace = trends.get("pace") or {}

        if pace.get("delta_percent") is not None:

            parts.append(f"pace {pace['delta_percent']:+.1f}%")

        if not parts:

            return ""

        return "Tendência (4 sem. vs 4 anteriores): " + ", ".join(parts)

    @staticmethod
    def _pace(pace_min_km: float | None) -> str:

        if pace_min_km is None:

            return "—"

        return f"{PaceFormatter.format(pace_min_km)} min/km"
