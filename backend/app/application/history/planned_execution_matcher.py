"""Pareia o treino PRESCRITO (`planned.steps`, os passos estruturados que a
IA emitiu e empurrou pro Garmin) com o EXECUTADO de verdade (as voltas já
ROTULADAS pelo relógio, `activity.raw["_garmin_typed_blocks"]`) — pra
QUALQUER tipo de treino (ritmado, progressivo, fartlek, longão), não só
intervalado.

Pareamento RÍGIDO por índice já foi tentado e descartado neste projeto
(dado real — relógio reiniciando, voltas-fantasma — mostrou que forçar 1:1
por posição casa bloco errado). Este matcher pareia em ORDEM mas com folga
(pequena janela de busca) e, em qualquer ambiguidade grande demais pra ter
certeza, devolve `None` — o chamador cai no comportamento de hoje (texto
livre pra IA alinhar por bom senso). Nunca fica pior, só mais preciso
quando dá pra confiar."""

from collections import Counter

from app.domain.entities.activity import Activity
from app.domain.entities.block_comparison import BlockComparison, ExecutedBlock
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import (
    COOLDOWN,
    INTERVAL,
    RECOVERY,
    REST,
    RUN,
    WARMUP,
    WorkoutStep,
)

# Aquecimento/desaquecimento vêm rotulados como "other" (tipo textual tipo
# WARMUP/COOLDOWN, confirmado no dump real de tiro -- não casam o padrão
# ACTIVE/INTERVAL). Corrida contínua (RUN) é diferente: um longão/rodagem
# de UM SÓ passo vem rotulada "effort" no dump real (o Garmin usa
# INTERVAL_ACTIVE até pra corrida sem estrutura nenhuma) -- por isso aceita
# os dois. Restringir WARMUP/COOLDOWN a só "other" evita que um aquecimento
# perdido "roube" por engano a volta de um tiro de verdade (que só é
# "effort") quando os dois competem pela mesma volta.
_KIND_MAP = {
    WARMUP: {"other"},
    COOLDOWN: {"other"},
    RUN: {"other", "effort"},
    INTERVAL: {"effort"},
    RECOVERY: {"recovery"},
    REST: {"recovery", "other"},
}

_LABEL_BASE = {
    WARMUP: "Aquecimento",
    COOLDOWN: "Desaquecimento",
    RUN: "Corrida contínua",
    INTERVAL: "Tiro",
    RECOVERY: "Recuperação",
    REST: "Pausa",
}

# tipos que são inerentemente repetidos -- sempre numerados, mesmo com 1 só
_ALWAYS_NUMBER = {INTERVAL, RECOVERY, REST}

# quantas voltas executadas à frente aceita pular procurando o próximo
# bloco compatível (tolera 1-2 voltas-fantasma/inesperadas no meio)
_LOOKAHEAD = 3

# blocos esperados sem par: acima disso o pareamento não é confiável, desiste
# (maioria faltando -- 1 bloco perdido num treino de 2-3 blocos é normal,
# ex.: aquecimento que o relógio não gravou; não é motivo pra desistir)
_GIVE_UP_RATIO = 0.5

# folga de pace (ruído de GPS/Garmin) e de distância/duração (variação
# natural de pacing) pro veredito "dentro do alvo"
_PACE_SLACK = 0.03
_AMOUNT_TOLERANCE = 0.15


class PlannedExecutionMatcher:

    @staticmethod
    def match(
        planned: PlannedSession,
        activity: Activity,
    ) -> BlockComparison | None:

        if not planned.steps:

            return None

        expected = PlannedExecutionMatcher._flatten(planned.steps)

        if not expected:

            return None

        executed = (activity.raw or {}).get("_garmin_typed_blocks")

        if not executed:

            return None

        blocks, missing, extra = PlannedExecutionMatcher._align(
            expected, executed
        )

        if not blocks or len(missing) > len(expected) * _GIVE_UP_RATIO:

            return None

        return BlockComparison(blocks=blocks, missing=missing, extra=extra)

    # ------------------------------------------------------------------

    @staticmethod
    def _flatten(steps: list[WorkoutStep]) -> list[dict]:
        """Achata os passos (expande REPEAT em N cópias sequenciais) e
        numera os rótulos (Tiro 1, Recuperação 1, Tiro 2...)."""

        flat: list[dict] = []

        def walk(items: list[WorkoutStep]) -> None:

            for step in items:

                if step.is_repeat:

                    for _ in range(step.reps or 0):

                        walk(step.steps)

                elif step.kind in _LABEL_BASE:

                    flat.append(
                        {
                            "kind": step.kind,
                            "distance_m": step.distance_m,
                            "duration_sec": step.duration_sec,
                            "pace_min": step.pace_min,
                            "pace_max": step.pace_max,
                        }
                    )

        walk(steps)

        counts = Counter(block["kind"] for block in flat)

        seen: Counter = Counter()

        for block in flat:

            seen[block["kind"]] += 1

            base = _LABEL_BASE[block["kind"]]

            if block["kind"] in _ALWAYS_NUMBER or counts[block["kind"]] > 1:

                block["label"] = f"{base} {seen[block['kind']]}"

            else:

                block["label"] = base

        return flat

    @staticmethod
    def _align(
        expected: list[dict],
        executed: list[dict],
    ) -> tuple[list[ExecutedBlock], list[str], int]:

        blocks: list[ExecutedBlock] = []

        missing: list[str] = []

        used = [False] * len(executed)

        cursor = 0

        for exp in expected:

            acceptable = _KIND_MAP.get(exp["kind"], set())

            match_idx = None

            for offset in range(_LOOKAHEAD + 1):

                idx = cursor + offset

                if idx >= len(executed):

                    break

                if used[idx]:

                    continue

                if executed[idx]["kind"] in acceptable:

                    match_idx = idx

                    break

            if match_idx is None:

                missing.append(exp["label"])

                continue

            used[match_idx] = True

            cursor = match_idx + 1

            blocks.append(
                PlannedExecutionMatcher._build_block(exp, executed[match_idx])
            )

        extra = len(executed) - sum(1 for flag in used if flag)

        return blocks, missing, extra

    @staticmethod
    def _build_block(exp: dict, ex: dict) -> ExecutedBlock:

        return ExecutedBlock(
            kind=exp["kind"],
            label=exp["label"],
            planned_distance_m=exp["distance_m"],
            planned_duration_sec=exp["duration_sec"],
            pace_min=exp["pace_min"],
            pace_max=exp["pace_max"],
            executed_distance_m=ex["distance_m"],
            executed_duration_sec=ex["duration_s"],
            executed_pace=ex.get("pace"),
            executed_hr=ex.get("avg_hr"),
            within_target=PlannedExecutionMatcher._within_target(exp, ex),
        )

    @staticmethod
    def _within_target(exp: dict, ex: dict) -> bool | None:

        pace_min = _parse_pace(exp["pace_min"])

        pace_max = _parse_pace(exp["pace_max"])

        executed_pace = ex.get("pace")

        if pace_min and pace_max and executed_pace:

            low = pace_min * (1 - _PACE_SLACK)

            high = pace_max * (1 + _PACE_SLACK)

            return low <= executed_pace <= high

        if exp["distance_m"]:

            return (
                abs(ex["distance_m"] - exp["distance_m"])
                <= exp["distance_m"] * _AMOUNT_TOLERANCE
            )

        if exp["duration_sec"]:

            return (
                abs(ex["duration_s"] - exp["duration_sec"])
                <= exp["duration_sec"] * _AMOUNT_TOLERANCE
            )

        return None


def _parse_pace(value: str | None) -> float | None:
    """'"M:SS"' (min/km) -> float minutos. Formato quebrado -> None, nunca
    levanta."""

    if not value:

        return None

    try:

        minutes, seconds = value.strip().split(":")

        return int(minutes) + int(seconds) / 60

    except (ValueError, AttributeError):

        return None
