from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RunnerBaseline:
    """Retrato REAL do corredor extraído do histórico do Strava — a base
    pra montar um plano fiel ao que ele de fato faz e progredir por cima.

    Não é o plano; é o ponto de partida (o "de onde ele está hoje")."""

    has_history: bool

    # Volume (km/semana): média recente, última semana e melhor semana.
    weekly_km: float
    last_week_km: float
    max_week_km: float

    # Frequência real: corridas por semana quando o atleta treina.
    runs_per_week: float

    # Distâncias reais: rodagem típica (mediana) e maior treino recente.
    typical_run_km: float
    longest_km: float

    # Tendência recente do volume: "subindo" | "estável" | "caindo".
    trend: str
