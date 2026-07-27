from app.application.history.metrics_resolver import MetricsResolver
from app.application.history.runner_baseline_builder import (
    RunnerBaselineBuilder,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory


def build_portrait(runner: RunnerProfile, history: TrainingHistory) -> str:
    """Retrato compacto do atleta pra IA decidir com base REAL — volume,
    tendência e paces derivados do histórico/evolução. Sem histórico
    utilizável, devolve string vazia (quem chama lida). Mesmo formato que o
    fluxo do furou-ontem usa."""

    try:

        baseline = RunnerBaselineBuilder.build(history, runner)

        metrics = MetricsResolver.resolve(runner, history)

        easy_min = PaceFormatter.format(metrics.easy_pace_min)
        easy_max = PaceFormatter.format(metrics.easy_pace_max)
        threshold = PaceFormatter.format(metrics.threshold_pace)
        vo2 = PaceFormatter.format(metrics.vo2_pace)

        return (
            f"Volume ~{baseline.weekly_km:.0f} km/sem "
            f"(última {baseline.last_week_km:.0f}, "
            f"melhor {baseline.max_week_km:.0f}), tendência {baseline.trend}. "
            f"Rodagem típica ~{baseline.typical_run_km:.0f} km; "
            f"maior treino ~{baseline.longest_km:.0f} km. "
            f"Paces (min/km): fácil {easy_min}-{easy_max}, "
            f"limiar {threshold}, VO2 {vo2}."
        )

    except Exception as e:

        print(f"Retrato do atleta falhou para '{runner.name}': {e}")

        return ""
