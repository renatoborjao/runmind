"""Narrador da PROVA: um parágrafo curto, emocional mas honesto, escrito pela
IA-treinadora ancorado SÓ nos fatos do dia (resultado vs meta, parciais/negative
split, FC, e o contexto adverso que o atleta superou — sono curto, gripe). É o
calor que o debrief determinístico não dá. Best-effort: se a IA falhar, volta
None e o debrief sai só com o veredito + números (nunca quebra).

Espelha o AIAnalysisWriter (saída estruturada blindada, thinking com teto,
fallback), mas o insumo é a PROVA, não um treino qualquer."""

import json

from google.genai import types

from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.core.config import get_settings
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)

THINKING_BUDGET = 256

MAX_OUTPUT_TOKENS = 800

# quão perto da meta ainda conta como "quase lá" (2% do tempo) — espelha o
# RaceDebrief pra o veredito da narrativa bater com o do relatório
_NEAR_MISS_RATIO = 1.02

NARRATIVE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "narrative": types.Schema(type=types.Type.STRING),
    },
    required=["narrative"],
)

PROMPT_TEMPLATE = """Você é o treinador de corrida comentando a PROVA que o \
atleta {name} acabou de correr — a prova que vocês vinham preparando. Escreva \
a NARRATIVA do dia: UM parágrafo curto (2 a 4 frases), na voz de um treinador \
brasileiro caloroso, emocional mas HONESTO.

FATOS DA PROVA (use SÓ isto, não invente nenhum número):
{facts}

REGRAS:
- Ancore-se nos NÚMEROS acima (tempo, pace, parciais, FC) — nada genérico que \
serviria pra qualquer prova.
- Comente a EXECUÇÃO: se veio em negative split (acelerou no fim), se controlou \
a FC, se segurou a ansiedade na largada — o que os fatos mostram.
- Se houver CONTEXTO ADVERSO (sono curto, gripe/doença, dor), VALORIZE a \
superação — correr bem apesar disso é mérito maior. Se não houver, não invente \
adversidade.
- Se houver "PORQUÊ DELE", conecte a conquista ao que a corrida significa pra \
ele — sem forçar.
- Celebre de verdade, mas sem exagero vazio; o resultado fala por si.
- NÃO repita a linha de números crua nem liste os splits um a um (isso já vai \
no relatório) — TRADUZA em leitura.

Responda APENAS com JSON: {{"narrative": "..."}}
"""


class RaceNarrativeWriter:

    @staticmethod
    async def write(profile: str, runner, enriched, goal) -> str | None:
        """A narrativa da prova, ou None (best-effort — o debrief não depende
        dela)."""

        try:

            facts = RaceNarrativeWriter._facts(profile, runner, enriched, goal)

            settings = get_settings()

            return await generate_json(
                model=settings.gemini_coach_model,
                contents=PROMPT_TEMPLATE.format(name=runner.name, facts=facts),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=NARRATIVE_SCHEMA,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET,
                    ),
                ),
                parse=RaceNarrativeWriter._parse,
            )

        except Exception as e:

            print(f"Narrador de prova falhou p/ '{profile}', fallback: {e}")

            return None

    # ------------------------------------------------------------------

    @staticmethod
    def _facts(profile: str, runner, enriched, goal) -> str:

        activity = enriched.activity

        distance_km = activity.distance / 1000
        actual_min = activity.moving_time / 60
        pace = PaceFormatter.format(actual_min / distance_km)

        lines = [
            f"Prova: {goal.race_label}",
            f"Distância: {distance_km:.2f} km",
            f"Tempo: {RaceNarrativeWriter._fmt(actual_min)}",
            f"Pace médio: {pace}/km",
        ]

        lines.append(RaceNarrativeWriter._verdict_fact(actual_min, goal))

        avg_hr = getattr(activity, "average_heartrate", None)

        if avg_hr:

            hr = f"FC média: {int(avg_hr)}"

            max_hr = getattr(activity, "max_heartrate", None)

            if max_hr:

                hr += f" (máx {int(max_hr)})"

            lines.append(f"{hr} bpm")

        structure = getattr(enriched, "structure", None)

        if structure is not None:

            if getattr(structure, "cadence_spm", None):

                lines.append(f"Cadência: {structure.cadence_spm} ppm")

            split_fact = RaceNarrativeWriter._splits_fact(structure)

            if split_fact:

                lines.append(split_fact)

        context = RaceNarrativeWriter._adverse_context(profile, activity)

        if context:

            lines.append(f"CONTEXTO ADVERSO: {context}")

        why = RaceNarrativeWriter._why(profile)

        if why:

            lines.append(f"PORQUÊ DELE: {why}")

        return "\n".join(lines)

    @staticmethod
    def _verdict_fact(actual_min: float, goal) -> str:

        target_min = RaceStrategyEngine._parse_time(goal.target_time)

        if target_min is None:

            return "Meta: sem tempo-alvo declarado (concluir a prova)"

        target = RaceNarrativeWriter._fmt(target_min)

        if actual_min <= target_min:

            return f"Resultado: BATEU a meta de {target} (ficou abaixo)"

        if actual_min <= target_min * _NEAR_MISS_RATIO:

            return f"Resultado: ficou MUITO perto da meta de {target}"

        return f"Resultado: acima da meta de {target} (não saiu o tempo hoje)"

    @staticmethod
    def _splits_fact(structure) -> str | None:
        """Descreve o padrão dos parciais (negative split?) sem despejar a lista
        inteira — a leitura, o número exato o relatório já mostra."""

        splits = getattr(structure, "km_splits", None)

        if not splits or len(splits) < 4:

            return None

        half = len(splits) // 2

        first = sum(splits[:half]) / half
        second = sum(splits[half:]) / (len(splits) - half)

        delta_sec = round((first - second) * 60)

        if delta_sec >= 3:

            pattern = f"negative split (2ª metade ~{delta_sec}s/km mais rápida)"

        elif delta_sec <= -5:

            pattern = f"caiu de ritmo no fim (~{abs(delta_sec)}s/km mais lento)"

        else:

            pattern = "ritmo constante do início ao fim"

        last = PaceFormatter.format(splits[-1])

        return f"Parciais: {pattern}; último km a {last}/km"

    @staticmethod
    def _adverse_context(profile: str, activity) -> str | None:
        """O que o atleta enfrentou no dia: sono curto (Garmin da noite) e
        doença/dor ATIVA na memória. Best-effort — sem dado, sem contexto."""

        facts: list[str] = []

        try:

            day = activity.start_date.date().isoformat()

            for health in GarminHealthRepository().load(profile):

                if health.date == day and health.sleep_hours is not None:

                    if health.sleep_hours < 6:

                        facts.append(
                            f"dormiu só {health.sleep_hours:.1f}h na noite anterior"
                        )

                    break

        except Exception:

            pass

        try:

            for entry in RunnerMemoryRepository().active(profile):

                if entry.category in ("lesao", "vida") and (
                    RaceNarrativeWriter._is_health_complaint(entry.content)
                ):

                    facts.append(entry.content.lower())

        except Exception:

            pass

        return "; ".join(facts) if facts else None

    # termos de doença/dor passageira que valem como contexto de superação
    _COMPLAINT_HINTS = (
        "gripe", "resfriad", "virose", "febre", "catarro", "gargant",
        "tosse", "covid", "sinusite", "rinite", "dor", "lesã", "lesao",
        "desconforto", "mal-estar", "mal estar", "indispost",
    )

    @staticmethod
    def _is_health_complaint(content: str) -> bool:

        text = content.lower()

        return any(hint in text for hint in RaceNarrativeWriter._COMPLAINT_HINTS)

    @staticmethod
    def _why(profile: str) -> str | None:
        """O porquê profundo do atleta (âncora emocional), se registrado."""

        try:

            reasons = [
                entry.content
                for entry in RunnerMemoryRepository().active(profile)
                if entry.category == "motivacao"
            ]

            return "; ".join(reasons) if reasons else None

        except Exception:

            return None

    @staticmethod
    def _fmt(minutes: float) -> str:

        total_sec = round(minutes * 60)
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)

        if h > 0:

            return f"{h}:{m:02d}:{s:02d}"

        return f"{m}:{s:02d}"

    @staticmethod
    def _parse(raw: str) -> str | None:
        """None em qualquer problema (pra o generate_json re-gerar)."""

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        if not isinstance(data, dict):

            return None

        narrative = data.get("narrative")

        if not isinstance(narrative, str) or not narrative.strip():

            return None

        return narrative.strip()
