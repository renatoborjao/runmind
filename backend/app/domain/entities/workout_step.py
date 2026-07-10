from __future__ import annotations

from dataclasses import dataclass, field

# Tipos de passo que o coach pode desenhar — cobrem qualquer treino que o
# Garmin aceita (e o que um treinador prescreve na vida real).
WARMUP = "warmup"
COOLDOWN = "cooldown"
RUN = "run"  # bloco principal contínuo (rodagem, longão, tempo)
INTERVAL = "interval"  # tiro (esforço)
RECOVERY = "recovery"  # trote/caminhada entre tiros
REST = "rest"  # parado
REPEAT = "repeat"  # grupo que repete N vezes (contém outros passos)

EXECUTABLE_KINDS = {WARMUP, COOLDOWN, RUN, INTERVAL, RECOVERY, REST}


@dataclass(slots=True)
class WorkoutStep:
    """Um passo estruturado do treino, agnóstico de plataforma. A partir
    dele a gente monta o treino guiado no Garmin E o texto da mensagem —
    uma fonte de verdade só.

    Fim do passo (escolhe um): distância (metros), duração (segundos) ou
    aberto (nenhum dos dois = avança no botão lap). Alvo (escolhe um):
    faixa de pace, faixa de FC ou nenhum. `repeat` usa `reps` + `steps`
    (os passos que se repetem)."""

    kind: str

    distance_m: float | None = None
    duration_sec: int | None = None

    # pace_min é o mais RÁPIDO, pace_max o mais LENTO (ex.: "4:45"/"4:50")
    pace_min: str | None = None
    pace_max: str | None = None

    hr_min: int | None = None
    hr_max: int | None = None

    # só para kind == "repeat"
    reps: int | None = None
    steps: list[WorkoutStep] = field(default_factory=list)

    @property
    def is_repeat(self) -> bool:

        return self.kind == REPEAT


def _to_meters(item: dict) -> float | None:

    if isinstance(item.get("distance_m"), (int, float)):

        return float(item["distance_m"])

    if isinstance(item.get("distance_km"), (int, float)):

        return round(float(item["distance_km"]) * 1000, 1)

    return None


def _to_seconds(item: dict) -> int | None:

    if isinstance(item.get("duration_sec"), (int, float)):

        return int(item["duration_sec"])

    if isinstance(item.get("duration_min"), (int, float)):

        return int(float(item["duration_min"]) * 60)

    return None


def _hr(item: dict, key: str) -> int | None:

    value = item.get(key)

    return int(value) if isinstance(value, (int, float)) else None


def parse_steps(raw) -> list[WorkoutStep]:
    """Lê a lista de passos que a IA emitiu (tolerante a lixo). Passo
    inválido é descartado; nunca levanta."""

    if not isinstance(raw, list):

        return []

    steps: list[WorkoutStep] = []

    for item in raw:

        if not isinstance(item, dict):

            continue

        kind = str(item.get("kind", "")).strip().lower()

        if kind == REPEAT:

            children = parse_steps(item.get("steps"))

            reps = item.get("reps")

            if not children or not isinstance(reps, int) or reps < 1:

                continue

            steps.append(
                WorkoutStep(kind=REPEAT, reps=reps, steps=children)
            )

            continue

        if kind not in EXECUTABLE_KINDS:

            continue

        steps.append(
            WorkoutStep(
                kind=kind,
                distance_m=_to_meters(item),
                duration_sec=_to_seconds(item),
                pace_min=(
                    str(item["pace_min"]).strip()
                    if item.get("pace_min")
                    else None
                ),
                pace_max=(
                    str(item["pace_max"]).strip()
                    if item.get("pace_max")
                    else None
                ),
                hr_min=_hr(item, "hr_min"),
                hr_max=_hr(item, "hr_max"),
            )
        )

    return steps
