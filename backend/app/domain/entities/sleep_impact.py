from dataclasses import dataclass


@dataclass(slots=True)
class SleepImpact:
    """O CUSTO real do sono curto no desempenho DELE — não conselho genérico.
    Compara a eficiência (pace no mesmo esforço) das corridas feitas após noites
    curtas vs bem-dormidas. `pace_cost_sec` = quantos s/km mais lento, no mesmo
    esforço, quando dormiu abaixo do piso. has_finding=False quando não há
    amostra/sinal suficiente. Ver [[project_ideias_produto]] (coaching de sono)."""

    has_finding: bool = False
    pace_cost_sec: int | None = None
    low_sleep_runs: int = 0
    rested_runs: int = 0
    threshold_hours: float = 7.0

    # True = comparação RELATIVA (noites mais curtas vs mais longas DELE), usada
    # quando o atleta quase nunca passa do piso saudável (crônico) e não haveria
    # grupo de contraste com o corte absoluto. Muda só o texto, não o método.
    relative: bool = False
