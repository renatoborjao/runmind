import json

from google.genai import types

from app.application.coach.context.coach_context import CoachContext
from app.application.coach.writer.labels import (
    intensity_label,
    plan_workout_label,
    workout_type_label,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.core.config import get_settings
from app.domain.entities.workout_structure import WorkoutStructure
from app.infrastructure.integrations.gemini.client import generate_text

MAX_OUTPUT_TOKENS = 700

# Quantas bullets a IA pode devolver na seção de análise.
MAX_BULLETS = 4

TREND_LABELS = {
    "negative": "acelerou no fim (negative split)",
    "even": "ritmo constante do início ao fim",
    "positive": "desacelerou no fim (apagou)",
    "unknown": "sem dado de progressão",
}

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente comentando o treino \
que ACABOU de sair de um atleta específico, por mensagem (WhatsApp). Escreva a \
seção de ANÁLISE: leitura honesta e ESPECÍFICA deste treino.

FATOS DO TREINO (use SÓ isto, não invente número nenhum):
{facts}

REGRAS:
- Comente o que ESTES dados mostram — principalmente a estrutura/splits (se \
houve tiros, se manteve o ritmo, se acelerou ou apagou no fim). Nada de frase \
genérica que serviria pra qualquer treino.
- NÃO contradiga os fatos. Se o treino foi um intervalado, trate como \
intervalado (não chame de leve).
- Se o executado bateu com o planejado, reconheça; se fugiu, aponte com \
naturalidade, sem bronca.
- ESTEIRA: quando o treino for na esteira, a distância e o pace do RELÓGIO \
podem divergir do real (o relógio estima). NÃO cobre diferença de distância \
nem de pace do relógio: use a DISTÂNCIA PLANEJADA como referência e assuma que \
o atleta cumpriu a prescrição. Foque em execução, FC/esforço, consistência dos \
tiros e recuperação.
- Tom de treinador de verdade: direto, humano, encorajador e útil. Fale com \
"você". Português do Brasil.
- 2 a {max_bullets} frases curtas, cada uma um ponto. Sem emojis, sem títulos.

Responda APENAS com JSON:
{{"analysis": ["frase 1", "frase 2"]}}
"""


class AIAnalysisWriter:
    """Escreve a seção de análise do feedback via IA, ancorada nos fatos
    determinísticos + na estrutura real do treino (splits/voltas). Se a IA
    falhar ou vier vazia, retorna None e o pipeline cai no texto
    determinístico — feedback nunca vira silêncio."""

    @staticmethod
    async def write(
        context: CoachContext,
    ) -> list[str] | None:

        try:

            facts = AIAnalysisWriter._facts(context)

            settings = get_settings()

            raw = await generate_text(
                model=settings.gemini_chat_model,
                contents=PROMPT_TEMPLATE.format(
                    facts=facts,
                    max_bullets=MAX_BULLETS,
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=0,
                    ),
                ),
                require_text=True,
            )

            return AIAnalysisWriter._parse(raw)

        except Exception as e:

            # IA fora do ar / JSON inválido / vazio: cai no determinístico
            print(f"IA falhou na análise do treino, fallback: {e}")

            return None

    @staticmethod
    def _parse(
        raw: str,
    ) -> list[str] | None:

        data = json.loads(raw)

        bullets = data.get("analysis") if isinstance(data, dict) else None

        if not isinstance(bullets, list):

            return None

        lines = [
            str(item).strip()
            for item in bullets
            if str(item).strip()
        ]

        if not lines:

            return None

        return lines[:MAX_BULLETS]

    @staticmethod
    def _facts(
        context: CoachContext,
    ) -> str:

        runner = context.runner

        executed = context.executed

        activity = executed.activity

        lines = [
            f"Atleta: {runner.name}",
            f"Meta: {runner.goal}",
        ]

        if context.planned is not None:

            planned = context.planned

            planned_line = plan_workout_label(
                planned.workout_type,
                planned.planned_distance_km,
            )

            if planned.planned_distance_km:

                planned_line += f" — {planned.planned_distance_km:.1f} km"

            lines.append(f"Planejado: {planned_line}")

            # prescrição (blocos/séries) pra IA comparar a execução com o
            # que foi pedido, não só distância crua
            if planned.structure:

                prescription = planned.structure.replace("\n", " | ")

                lines.append(f"Prescrição do plano: {prescription}")

        else:

            lines.append("Planejado: (treino extra, sem sessão no plano)")

        if executed.indoor:

            lines.append(
                "Ambiente: ESTEIRA — distância/pace do relógio podem "
                "divergir do real; a referência de distância é a do plano."
            )

        lines.append(
            f"Executado: {activity.distance / 1000:.1f} km, "
            f"pace médio {PaceFormatter.format(executed.pace_min_km)} min/km, "
            f"tipo identificado {workout_type_label(executed.training_type)}, "
            f"intensidade {intensity_label(executed.intensity)}, "
            f"zona {executed.estimated_zone}"
        )

        if activity.average_heartrate:

            hr = f"FC média {int(activity.average_heartrate)}"

            if activity.max_heartrate:

                hr += f", máx {int(activity.max_heartrate)}"

            lines.append(hr + " bpm")

        lines.append(
            AIAnalysisWriter._structure_facts(executed.structure)
        )

        return "\n".join(lines)

    @staticmethod
    def _structure_facts(
        structure: WorkoutStructure | None,
    ) -> str:

        if structure is None or (
            not structure.has_detail and structure.interval is None
        ):

            return "Estrutura: sem splits (esteira ou atividade resumida)"

        # intervalado detectado no stream: descreve os tiros e a FC (é o
        # que revela se o atleta respeitou o treino de tiro)
        if structure.interval is not None:

            interval = structure.interval

            reps = "; ".join(
                f"tiro {i + 1}: {rep['distance_m']}m a "
                f"{PaceFormatter.format(rep['pace'])}"
                + (f" (pico {rep['peak_hr']}bpm)" if rep.get("peak_hr") else "")
                for i, rep in enumerate(interval.reps)
            )

            hr = ""

            if interval.avg_peak_hr:

                hr = (
                    f"; FC pico média {interval.avg_peak_hr}bpm"
                    + (
                        f", recuperação {interval.avg_recovery_hr}bpm"
                        if interval.avg_recovery_hr
                        else ""
                    )
                )

            cadence = (
                f"; cadência {structure.cadence_spm} ppm"
                if structure.cadence_spm
                else ""
            )

            return (
                f"Estrutura: INTERVALADO com {interval.rep_count} tiros "
                f"(pace médio {PaceFormatter.format(interval.avg_rep_pace)}"
                f"/km){hr}{cadence}. Reps — {reps}"
            )

        parts = []

        if structure.km_splits:

            splits = ", ".join(
                f"km{i + 1} {PaceFormatter.format(pace)}"
                for i, pace in enumerate(structure.km_splits)
            )

            parts.append(f"splits: {splits}")

        parts.append(
            "intervalado (tiros alternados)"
            if structure.is_interval
            else "ritmo sem tiros"
        )

        parts.append(
            f"progressão: {TREND_LABELS.get(structure.split_trend)}"
        )

        if structure.cadence_spm:

            parts.append(f"cadência {structure.cadence_spm} ppm")

        return "Estrutura: " + "; ".join(parts)
