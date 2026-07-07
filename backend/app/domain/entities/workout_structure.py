from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.interval_analysis import IntervalAnalysis


@dataclass(slots=True)
class WorkoutStructure:
    """Retrato da estrutura INTERNA do treino, derivado dos splits por km
    e das voltas (laps) que o Strava manda no detalhe da atividade — o que
    a média sozinha esconde (tiros, negative split, apagada no fim).

    Quando o treino vem sem esse detalhe (esteira sem splits, atividade
    resumida), `has_detail` é False e os campos ricos ficam vazios; nunca
    quebra, só empobrece a análise."""

    # pace (min/km) de cada km, na ordem do treino
    km_splits: list[float]

    # FC média de cada km (alinhada a km_splits; None onde faltou FC)
    km_hr: list[int | None]

    # voltas manuais relevantes (>= 300 m): quantas e o pace de cada
    lap_count: int
    lap_paces: list[float]

    # variabilidade entre os kms
    fastest_km_pace: float | None
    slowest_km_pace: float | None
    pace_spread: float | None  # (mais lento - mais rápido) / mais rápido

    # "negative" (acelerou no fim) | "even" | "positive" (apagou) | "unknown"
    split_trend: str

    # tiros alternados detectados pela variação entre voltas/kms
    is_interval: bool

    # passos por minuto (Strava dá RPM por perna; aqui já em passos/min)
    cadence_spm: int | None

    hr_avg: int | None
    hr_max: int | None

    # há splits/laps pra analisar?
    has_detail: bool

    # análise dos tiros a partir do stream (None quando não há stream ou
    # o treino não é intervalado)
    interval: IntervalAnalysis | None = None
