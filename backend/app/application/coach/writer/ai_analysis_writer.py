import json
import re

from google.genai import types

from app.application.coach.context.coach_context import CoachContext
from app.application.coach.writer.labels import (
    intensity_label,
    plan_workout_label,
    workout_type_label,
)
from app.application.external_plan.treino_online_legend import (
    legend_for_prompt,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.core.config import get_settings
from app.domain.entities.workout_structure import WorkoutStructure
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# Pro pensa (thinking) e isso conta no orçamento de saída + é cobrado como
# output. Teto de thinking EXPLÍCITO + max_output com folga pra caber
# thinking + a análise (senão o thinking come tudo e volta vazio).
THINKING_BUDGET = 512

MAX_OUTPUT_TOKENS = 2000

# Quantas bullets a IA pode devolver na seção de análise.
MAX_BULLETS = 4

# Fatos SEM veredito: "apagou/quebrou" é conclusão, não dado — quando o
# rótulo já vinha com julgamento, a IA amplificava (+4% virava "você
# quebrou"). O grau fica no fato; a leitura fica com a IA.
TREND_LABELS = {
    "negative": "acelerou no fim (negative split)",
    "even": "ritmo constante do início ao fim",
    "positive_mild": (
        "segunda metade um pouco mais lenta que a primeira "
        "(diferença pequena, faixa de variação normal)"
    ),
    "positive": "queda acentuada de ritmo na segunda metade",
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
- Se houver "Execução por bloco", COMPARE os blocos executados com a \
estrutura PRESCRITA (use a legenda pra decodificar as siglas). O atleta pode \
ter CUMPRIDO a estrutura (ex.: alternou 3' corrida / 2' caminhada) mesmo que \
os splits por km pareçam constantes — os blocos revelam isso; não afirme que \
ele "não fez" o treino sem olhar os blocos. Se cumpriu os blocos mas com \
pouco contraste (recuperação rápida demais), aponte ISSO, não a ausência.
- ESTEIRA: quando o treino for na esteira, a distância e o pace do RELÓGIO \
podem divergir do real (o relógio estima). NÃO cobre diferença de distância \
nem de pace do relógio: use a DISTÂNCIA PLANEJADA como referência e assuma que \
o atleta cumpriu a prescrição. Foque em execução, FC/esforço, consistência dos \
tiros e recuperação.
- VOCABULÁRIO DE RITMO: só use palavras como "quebrou", "apagou" ou "não \
aguentou" se os fatos disserem "queda ACENTUADA de ritmo". Segunda metade \
"um pouco mais lenta" é variação normal de treino (subida, calor, semáforo) \
— trate como normal, sem tom de falha.
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

            # generate_json re-gera se o JSON vier torto (o modelo escorrega
            # às vezes) — a análise é o coração do produto, não pode cair no
            # genérico à toa. Só cai no fallback se TODAS as tentativas
            # falharem.
            return await generate_json(
                model=settings.gemini_coach_model,
                contents=PROMPT_TEMPLATE.format(
                    facts=facts,
                    max_bullets=MAX_BULLETS,
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET,
                    ),
                ),
                parse=AIAnalysisWriter._parse,
            )

        except Exception as e:

            # IA fora do ar / JSON inválido / vazio: cai no determinístico
            print(f"IA falhou na análise do treino, fallback: {e}")

            return None

    @staticmethod
    def _parse(
        raw: str,
    ) -> list[str] | None:
        """Repara + valida a resposta. Devolve None em QUALQUER problema
        (JSON torto, estrutura errada, vazio) pra o generate_json re-gerar."""

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        bullets = data.get("analysis") if isinstance(data, dict) else None

        if not isinstance(bullets, list):

            return None

        lines = [
            str(item).strip()
            for item in bullets
            if str(item).strip()
        ]

        return lines[:MAX_BULLETS] if lines else None

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

            # prescrição (blocos/séries) pra IA comparar a execução com o que
            # foi pedido, não só distância crua. Treinador externo guarda a
            # prescrição em `notes` (com siglas do "Treino Online"), não em
            # `structure` — aí manda a LEGENDA junto pra IA decodificar
            # (CCR/CCL/FF/CAM...) e comparar com o executado.
            prescription = planned.structure or planned.notes

            if prescription:

                lines.append(
                    "Prescrição do treinador: "
                    + prescription.strip().replace("\n", " | ")[:700]
                )

                if not planned.structure and planned.notes:

                    lines.append(
                        "Legenda das siglas do treinador:\n"
                        + legend_for_prompt()
                    )

            # execução POR BLOCO (voltas do Garmin) pra IA comparar com a
            # estrutura prescrita. Decisivo no treinador externo: o treino é
            # estruturado (5×3'/2', HIIT 2×2k...) e os splits por km achatam
            # a estrutura — o atleta pode ter CUMPRIDO os blocos.
            if planned.notes:

                laps_fact = AIAnalysisWriter._executed_laps_fact(
                    (activity.raw or {}).get("_garmin_laps") or []
                )

                if laps_fact:

                    lines.append(laps_fact)

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

        # tudo que o Garmin mediu no relógio — deixa a leitura DE ACORDO com
        # o executado (efeito de treino, percepção do atleta, dinâmica de
        # corrida, potência, carga). Só aparece pra quem treina com Garmin.
        garmin = AIAnalysisWriter._garmin_facts(
            (activity.raw or {}).get("_garmin_metrics")
        )

        if garmin:

            lines.append(garmin)

        return "\n".join(lines)

    # sensação do atleta (directWorkoutFeel do Garmin, 0-100 em passos de 25)
    _FEEL_WORDS = {
        0: "muito cansado", 25: "cansado", 50: "normal",
        75: "bem", 100: "forte",
    }

    @staticmethod
    def _executed_laps_fact(laps: list[dict]) -> str:
        """Formata as voltas EXECUTADAS (duração + distância + pace + FC) pra
        IA alinhar com a prescrição. A prescrição vem em tempo (3'/2'), então
        a duração de cada volta é a chave do casamento."""

        parts = []

        for lap in laps:

            dur = lap.get("duration_s") or 0

            if not dur or not lap.get("distance_m"):

                continue

            minutes, seconds = divmod(int(dur), 60)

            seg = f"{minutes}'{seconds:02d} {lap['distance_m']}m"

            if lap.get("pace"):

                seg += f" {PaceFormatter.format(lap['pace'])}/km"

            if lap.get("avg_hr"):

                seg += f" FC{lap['avg_hr']}"

            parts.append(seg)

        if not parts:

            return ""

        return (
            "Execução por bloco (voltas do relógio, compare com a prescrição "
            "acima): " + "; ".join(parts)
        )

    @staticmethod
    def _clean_msg(msg) -> str | None:
        """Enum do Garmin ('OVERREACHING_14') -> texto legível
        ('overreaching') — tira o código no fim e troca '_' por espaço."""

        if not msg:

            return None

        text = re.sub(r"_\d+$", "", str(msg)).replace("_", " ").lower().strip()

        return text or None

    @staticmethod
    def _garmin_facts(metrics: dict | None) -> str | None:
        """Formata TODO o bundle rico do Garmin que faz sentido pra análise —
        só os campos presentes (cada treino/relógio traz um subconjunto)."""

        if not metrics:

            return None

        parts = []

        # --- efeito de treino (o estímulo que o treino gerou) ---
        te = metrics.get("training_effect")

        if te is not None:

            detail = " / ".join(
                x for x in (
                    metrics.get("training_effect_label"),
                    AIAnalysisWriter._clean_msg(metrics.get("aerobic_effect_msg")),
                ) if x
            )

            parts.append(
                f"efeito aeróbico {te}/5" + (f" ({detail})" if detail else "")
            )

        ana = metrics.get("anaerobic_effect")

        if ana is not None:

            msg = AIAnalysisWriter._clean_msg(metrics.get("anaerobic_effect_msg"))

            parts.append(
                f"efeito anaeróbico {ana}/5" + (f" ({msg})" if msg else "")
            )

        # --- percepção do atleta ---
        if metrics.get("workout_rpe"):

            parts.append(
                f"esforço percebido (RPE) {round(metrics['workout_rpe'] / 10)}/10"
            )

        feel = metrics.get("workout_feel")

        if feel is not None:

            word = AIAnalysisWriter._FEEL_WORDS.get(round(feel / 25) * 25)

            parts.append(f"sensação do atleta: {word or feel}")

        # --- pace ajustado ao relevo (esforço real em subida/descida) ---
        gap = metrics.get("grade_adjusted_speed")

        if gap:

            parts.append(
                f"pace ajustado ao relevo "
                f"{PaceFormatter.format((1000 / gap) / 60)} min/km"
            )

        # --- dinâmica de corrida (forma) ---
        dynamics = []

        if metrics.get("ground_contact_ms"):

            dynamics.append(
                f"contato com o solo {round(metrics['ground_contact_ms'])} ms"
            )

        if metrics.get("stride_length_cm"):

            dynamics.append(f"passada {round(metrics['stride_length_cm'])} cm")

        if metrics.get("vertical_oscillation_cm"):

            dynamics.append(
                f"oscilação vertical {metrics['vertical_oscillation_cm']:.1f} cm"
            )

        if metrics.get("vertical_ratio"):

            dynamics.append(f"razão vertical {metrics['vertical_ratio']:.1f}%")

        if dynamics:

            parts.append("dinâmica de corrida: " + ", ".join(dynamics))

        # --- potência ---
        if metrics.get("avg_power"):

            extras = []

            if metrics.get("normalized_power"):

                extras.append(f"normalizada {round(metrics['normalized_power'])} W")

            if metrics.get("max_power"):

                extras.append(f"máx {round(metrics['max_power'])} W")

            parts.append(
                f"potência média {round(metrics['avg_power'])} W"
                + (f" ({', '.join(extras)})" if extras else "")
            )

        # --- carga / gasto ---
        if metrics.get("body_battery_delta") is not None:

            parts.append(f"body battery {metrics['body_battery_delta']:+d}")

        intensity = []

        if metrics.get("vigorous_minutes"):

            intensity.append(f"{metrics['vigorous_minutes']} vigorosos")

        if metrics.get("moderate_minutes"):

            intensity.append(f"{metrics['moderate_minutes']} moderados")

        if intensity:

            parts.append("minutos de intensidade: " + " + ".join(intensity))

        if metrics.get("calories"):

            parts.append(f"{round(metrics['calories'])} kcal")

        # --- ambiente ---
        temp = metrics.get("avg_temperature")

        if temp is not None:

            line = f"temperatura ~{round(temp)}°C"

            if metrics.get("max_temperature"):

                line += f" (máx {round(metrics['max_temperature'])}°C)"

            parts.append(line)

        if not parts:

            return None

        return (
            "Dados do Garmin (medidos no relógio, de acordo com o "
            "executado): " + "; ".join(parts)
        )

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

            # pace + FC por km: sem a FC a IA já "viu" fadiga em treino
            # onde a FC CAIU na segunda metade (pace estável + FC caindo
            # = eficiência, não cansaço)
            hr_by_km = structure.km_hr or []

            splits = ", ".join(
                f"km{i + 1} {PaceFormatter.format(pace)}"
                + (
                    f" ({hr_by_km[i]}bpm)"
                    if i < len(hr_by_km) and hr_by_km[i]
                    else ""
                )
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
